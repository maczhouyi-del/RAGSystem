import type { Evidence, SupportingPair } from "./api";
import { isDesktop, openPaperPdf } from "./transport";
import { errorMessage } from "./errors";

type PagedSource = {
  page_start: number;
  page_end?: number;
  page_location?: "available" | "unavailable";
};
const validPage = (page: number | undefined): page is number =>
  page !== undefined && Number.isInteger(page) && page >= 1 && page <= 99999;
export function targetPage(source: PagedSource): number | undefined {
  return source.page_location !== "unavailable" && validPage(source.page_start)
    ? source.page_start
    : undefined;
}
export function pageLabel(source: PagedSource): string {
  const start = targetPage(source);
  if (start === undefined) return "页码未知";
  return validPage(source.page_end) && source.page_end > start
    ? `p.${start}–${source.page_end}`
    : `p.${start}`;
}
export function PdfLink({
  paperId,
  page,
  label,
  onError,
}: {
  paperId: string;
  page?: number;
  label: string;
  onError: (message: string) => void;
}) {
  const target = validPage(page) ? page : undefined;
  const path = `/api/papers/${encodeURIComponent(paperId)}/pdf${target === undefined ? "" : `#page=${target}`}`;
  return (
    <a
      href={path}
      target="_blank"
      rel="noreferrer"
      onClick={(event) => {
        if (isDesktop()) {
          event.preventDefault();
          void openPaperPdf(paperId, target).catch((error) =>
            onError(
              errorMessage(
                error instanceof Error ? error.message : "request_failed",
              ),
            ),
          );
        }
      }}
    >
      {label}
    </a>
  );
}
export function PdfNavigation({
  source,
  paperId,
  onError,
}: {
  source: Pick<
    Evidence,
    "page_start" | "page_end" | "page_location" | "pdf_regions"
  >;
  paperId: string;
  onError: (message: string) => void;
}) {
  const regionPages = [
    ...new Set(
      source.pdf_regions
        .map((region) => region.page_no)
        .filter((page): page is number => validPage(page ?? undefined)),
    ),
  ].sort((a, b) => a - b);
  const start = targetPage(source);
  const end =
    validPage(source.page_end) &&
    start !== undefined &&
    source.page_end >= start
      ? source.page_end
      : start;
  const pages = regionPages.length
    ? regionPages
    : start === undefined
      ? []
      : Array.from(
          { length: Math.min(10, (end ?? start) - start + 1) },
          (_, index) => start + index,
        );
  if (!regionPages.length && end !== undefined && pages.at(-1) !== end)
    pages.push(end);
  const boxes = source.pdf_regions.filter(
    (region) => region.bbox !== null,
  ).length;
  return (
    <section aria-label="PDF 来源定位" className="pdf-navigation">
      <h4>核查原始 PDF</h4>
      <p>
        {boxes
          ? `保留 ${boxes} 个元素区域，仅用于定位；不表示逐字结论高亮。`
          : "精确 PDF 坐标不可用，请按页码和原文搜索定位。"}
      </p>
      {source.pdf_regions.some((region) => region.bbox === null) &&
        boxes > 0 && <p>部分来源区域不可用；请核对全部候选页和辅助原文。</p>}
      {pages.length > 0 ? (
        <div className="inline" aria-label="候选来源页">
          {pages.slice(0, 11).map((page) => (
            <PdfLink
              key={page}
              paperId={paperId}
              page={page}
              label={`打开候选页 ${page}`}
              onError={onError}
            />
          ))}
        </div>
      ) : (
        <p>来源页码未知。打开论文后，用下方原文在阅读器中搜索。</p>
      )}
      {regionPages.length > 11 ||
      (!regionPages.length &&
        start !== undefined &&
        end !== undefined &&
        end - start >= 10) ? (
        <p>候选页较多，仅显示部分入口；请核查完整页码范围。</p>
      ) : null}
    </section>
  );
}
export function SupportedQuote({
  source,
  pairs,
}: {
  source: Evidence;
  pairs: SupportingPair[];
}) {
  const original = Array.from(source.content ?? "");
  const quote = Array.from(source.quote);
  const start = source.span_start,
    end = source.span_end;
  const exact =
    start !== undefined &&
    end !== undefined &&
    Number.isInteger(start) &&
    Number.isInteger(end) &&
    start >= 0 &&
    end > start &&
    end <= original.length &&
    original.slice(start, end).join("") === source.quote;
  const ranges = exact
    ? pairs
        .filter((pair) => pair.evidence_id === source.evidence_id)
        .flatMap((pair) => {
          const a = pair.supporting_span_start,
            b = pair.supporting_span_end;
          return a !== null &&
            a !== undefined &&
            b !== null &&
            b !== undefined &&
            Number.isInteger(a) &&
            Number.isInteger(b) &&
            a >= start &&
            b > a &&
            b <= end
            ? [[a - start, b - start]]
            : [];
        })
    : [];
  const parts: { text: string; marked: boolean }[] = [];
  for (const [index, character] of quote.entries()) {
    const marked = ranges.some(([a, b]) => index >= a && index < b);
    if (parts.at(-1)?.marked === marked)
      parts[parts.length - 1].text += character;
    else parts.push({ text: character, marked });
  }
  return (
    <>
      {ranges.length > 0 && (
        <p>
          原文中标记了自动核查支持片段。高亮仅对应下方文字，原始 PDF
          请另行核查。
        </p>
      )}
      <blockquote aria-label="主引用原文">
        {parts.map((part, index) =>
          part.marked ? <mark key={index}>{part.text}</mark> : part.text,
        )}
      </blockquote>
    </>
  );
}
