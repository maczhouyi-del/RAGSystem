import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import { EntityReview } from "./EntityReview";
import { api, PdfLocation } from "./api";
import { PdfLink, pageLabel, targetPage } from "./PdfReading";
import type { Filters } from "./components";

const Coverage = z.object({
  total_chunks: z.number().int().nonnegative(),
  reviewed_chunks: z.number().int().nonnegative(),
  linked_chunks: z.number().int().nonnegative(),
  active_chunks: z.number().int().nonnegative(),
  failed_chunks: z.number().int().nonnegative(),
  needs_review_chunks: z.number().int().nonnegative().default(0),
  matching_chunks: z.number().int().nonnegative(),
  strict: z.boolean(),
  complete: z.boolean(),
});
const Annotations = Coverage.omit({
  matching_chunks: true,
  strict: true,
  complete: true,
}).extend({
  paper_id: z.string().uuid(),
  status: z.enum([
    "unprocessed",
    "processing",
    "partial",
    "completed",
    "failed",
  ]),
  items: z.array(
    z.object({
      entity_id: z.string().uuid(),
      name: z.string(),
      entity_type: z.string(),
      chunk_id: z.string().uuid(),
      section_path: z.string(),
      page_start: z.number(),
      page_end: z.number(),
      page_location: PdfLocation.page_location,
    }),
  ),
  total_occurrences: z.number().int().nonnegative(),
  limit: z.number().int(),
  offset: z.number().int(),
});
const Source = z.object({
  ...PdfLocation,
  paper_id: z.string().uuid(),
  chunk_id: z.string().uuid(),
  section_id: z.string().uuid(),
  section_path: z.string(),
  page_start: z.number(),
  page_end: z.number(),
  content: z.string(),
});
const labels = {
  unprocessed: "未处理",
  processing: "处理中",
  partial: "部分完成",
  completed: "完成",
  failed: "失败",
};
const kinds: Record<string, string> = {
  dataset: "数据集",
  method: "方法",
  metric: "指标",
};

export function EntityFilterNotice({ filters }: { filters: Filters }) {
  const [coverage, setCoverage] = useState<z.infer<typeof Coverage> | null>(
    null,
  );
  const [error, setError] = useState("");
  const serialized = JSON.stringify(filters);
  const strict = [
    filters.datasets,
    filters.methods,
    filters.metrics,
    filters.entity_types,
  ].some((values) => values.length > 0);
  useEffect(() => {
    setCoverage(null);
    setError("");
    if (!strict) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      void api(
        "/api/annotations/coverage",
        Coverage,
        JSON.parse(serialized),
        "POST",
        controller.signal,
      )
        .then((value) => {
          if (!controller.signal.aborted) setCoverage(value);
        })
        .catch(() => {
          if (!controller.signal.aborted)
            setError(
              "标注覆盖状态读取失败，无法确认完整性；严格条件仍然保留。",
            );
        })
        .finally(() => clearTimeout(deadline));
    }, 400);
    const deadline = setTimeout(() => {
      controller.abort();
      setError("标注覆盖状态读取超时，无法确认完整性；严格条件仍然保留。");
    }, 10000);
    return () => {
      clearTimeout(timer);
      clearTimeout(deadline);
      controller.abort();
    };
  }, [serialized, strict]);
  return (
    <div aria-label="实体过滤语义">
      <p>
        datasets / methods / metrics / entity_types
        是精确实体过滤：仅匹配已有标注的名称（忽略大小写），不是全文搜索。问题中的普通文本用于检索，不会证明实体已完整标注。
      </p>
      {strict && !coverage && !error && (
        <p role="status">正在检查当前范围的标注覆盖…</p>
      )}
      {error && <p role="alert">{error}</p>}
      {coverage && (
        <>
          <p>
            当前范围 {coverage.total_chunks} 个片段，明确审阅{" "}
            {coverage.reviewed_chunks} 个，有实体链接 {coverage.linked_chunks}{" "}
            个；严格匹配 {coverage.matching_chunks} 个。
          </p>
          {coverage.matching_chunks === 0 && (
            <p role="alert">
              当前严格实体过滤不可满足：没有匹配的已标注片段。不会自动放宽条件；你可以明确清除实体条件后进行普通文本检索。
            </p>
          )}
          {!coverage.complete && (
            <p role="alert">
              实体标注覆盖不完整；未标注不代表不存在该数据集、方法或指标，过滤结果不能视为完整。
            </p>
          )}
          {coverage.complete && (
            <p>覆盖已完成仍不代表提取准确或原文不存在其他实体，请核对来源。</p>
          )}
        </>
      )}
    </div>
  );
}

export function PaperAnnotations({
  paperId,
  title,
}: {
  paperId: string;
  title: string;
}) {
  const [open, setOpen] = useState(false),
    [data, setData] = useState<z.infer<typeof Annotations> | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [source, setSource] = useState<z.infer<typeof Source> | null>(null),
    [sourceError, setSourceError] = useState("");
  const generation = useRef(0),
    sourceGeneration = useRef(0);
  const controller = useRef<AbortController | null>(null),
    sourceController = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      generation.current++;
      sourceGeneration.current++;
      controller.current?.abort();
      sourceController.current?.abort();
    },
    [paperId],
  );
  async function load(offset = 0) {
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    const version = ++generation.current;
    setBusy(true);
    setData(null);
    setSource(null);
    setSourceError("");
    setError("");
    sourceGeneration.current++;
    sourceController.current?.abort();
    const timeout = setTimeout(() => abort.abort(), 10000);
    try {
      const value = await api(
        `/api/papers/${paperId}/annotations?limit=50&offset=${offset}`,
        Annotations,
        undefined,
        "GET",
        abort.signal,
      );
      if (generation.current === version && !abort.signal.aborted)
        setData(value);
    } catch {
      if (generation.current === version)
        setError(
          "实体标注状态读取失败，状态未知；请刷新，不能据此判断实体不存在。",
        );
    } finally {
      clearTimeout(timeout);
      if (generation.current === version) setBusy(false);
    }
  }
  async function showSource(chunk: string) {
    sourceController.current?.abort();
    const abort = new AbortController();
    sourceController.current = abort;
    const version = ++sourceGeneration.current;
    setSource(null);
    setSourceError("");
    const timeout = setTimeout(() => abort.abort(), 10000);
    try {
      const value = await api(
        `/api/papers/${paperId}/chunks/${chunk}/source`,
        Source,
        undefined,
        "GET",
        abort.signal,
      );
      if (version === sourceGeneration.current && !abort.signal.aborted)
        setSource(value);
    } catch {
      if (version === sourceGeneration.current)
        setSourceError("来源读取失败或已移除，请重新核对论文。");
    } finally {
      clearTimeout(timeout);
    }
  }
  return (
    <details
      onToggle={(event) => {
        if (event.target !== event.currentTarget) return;
        const expanded = event.currentTarget.open;
        setOpen(expanded);
        if (expanded) void load();
        else {
          generation.current++;
          sourceGeneration.current++;
          controller.current?.abort();
          sourceController.current?.abort();
          setData(null);
          setSource(null);
          setBusy(false);
        }
      }}
    >
      <summary>
        {title} 实体标注：{data ? labels[data.status] : "状态未读取"}
      </summary>
      {open && (
        <>
          <button disabled={busy} onClick={() => void load()}>
            刷新实体标注
          </button>
          {busy && <p role="status">正在读取实体标注…</p>}
          {error && <p role="alert">{error}</p>}
          <EntityReview paperId={paperId} onChanged={() => void load()} />
          {data && (
            <>
              <p>
                实体标注：{labels[data.status]} · 明确审阅{" "}
                {data.reviewed_chunks} / {data.total_chunks} 片段 · 有实体链接{" "}
                {data.linked_chunks} · 处理中 {data.active_chunks} · 失败{" "}
                {data.failed_chunks} · 待人工审阅 {data.needs_review_chunks}
              </p>
              <p>
                {data.status === "completed"
                  ? "审阅覆盖完成不代表提取准确，请核对来源。"
                  : "标注覆盖未完成；没有标注不代表论文没有相应实体。"}
              </p>
              {data.items.length === 0 && (
                <p>当前页没有已识别实体，不能据此判断原文不存在实体。</p>
              )}
              <ul>
                {data.items.map((item) => (
                  <li key={`${item.chunk_id}:${item.entity_id}`}>
                    {kinds[item.entity_type] ?? item.entity_type}：{item.name} ·{" "}
                    {item.section_path} · {pageLabel(item)}{" "}
                    <button onClick={() => void showSource(item.chunk_id)}>
                      查看 {item.name} 来源片段
                    </button>
                  </li>
                ))}
              </ul>
              <p>
                共 {data.total_occurrences} 条实体与片段关联；第{" "}
                {Math.floor(data.offset / 50) + 1} 页
              </p>
              <button
                disabled={busy || data.offset === 0}
                onClick={() => void load(Math.max(0, data.offset - 50))}
              >
                上一页实体
              </button>
              <button
                disabled={
                  busy || data.offset + data.limit >= data.total_occurrences
                }
                onClick={() => void load(data.offset + 50)}
              >
                下一页实体
              </button>
            </>
          )}
          {sourceError && <p role="alert">{sourceError}</p>}
          {source && (
            <div aria-label="实体来源片段">
              <p>
                {source.section_path} · {pageLabel(source)} · {source.chunk_id}
              </p>
              <pre className="annotation-source">{source.content}</pre>
              <PdfLink
                paperId={paperId}
                page={targetPage(source)}
                label="打开来源 PDF"
                onError={setSourceError}
              />
              <p>
                这是关联的原始片段。请在人工校正面板核对精确跨度；旧关联没有跨度时，不能据名称推断已核验。
              </p>
              <button onClick={() => setSource(null)}>关闭来源片段</button>
            </div>
          )}
        </>
      )}
    </details>
  );
}
