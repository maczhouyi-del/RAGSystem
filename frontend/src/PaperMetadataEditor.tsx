import { useState } from "react";
import { z } from "zod";
import { Paper, api } from "./api";
import { SourceProvenance } from "./components";

type PaperData = z.infer<typeof Paper>;
const labels: Record<string, string> = {
  title: "标题",
  authors: "作者",
  year: "年份",
  venue: "会议/期刊",
};

export function OriginalMetadata({ paper }: { paper: PaperData }) {
  const source = paper.original_metadata;
  return (
    <details className="paper-original-metadata">
      <summary>
        导入时的元数据：
        {source
          ? source.kind === "arxiv_atom"
            ? "arXiv 返回值"
            : "用户上传填写值"
          : "未保存"}
      </summary>
      {source ? (
        <>
          <p>
            原始标题：{source.values.title}
            <br />
            原始作者：{source.values.authors.join("; ") || "未记录"}
            <br />
            原始年份：{source.values.year ?? "未记录"}
            <br />
            原始会议/期刊：{source.values.venue ?? "未记录"}
          </p>
          <p>
            记录时间：{source.captured_at}
            <br />原 PDF SHA256：<code>{source.pdf_sha256}</code>
          </p>
          {source.arxiv_id && (
            <p>
              原始 arXiv 标识：{source.arxiv_id}；版本：
              {source.arxiv_version ?? "未记录"}
            </p>
          )}
          <p>
            {source.kind === "arxiv_atom"
              ? "保留实际获取的来源字段；用户校正不会覆盖这份记录。"
              : "这是上传时用户填写的元数据，不代表出版方的官方元数据。"}
          </p>
        </>
      ) : (
        <p>
          旧记录未保存导入时的元数据，不能推断官方值。论文来源与版本仍以已有记录为准。
        </p>
      )}
    </details>
  );
}

function draft(paper: PaperData) {
  return {
    title: paper.title,
    authors: paper.authors.join("; "),
    year: paper.year === null ? "" : String(paper.year),
    venue: paper.venue ?? "",
  };
}

export function PaperMetadataEditor({
  paper,
  onSaved,
  onClose,
}: {
  paper: PaperData;
  onSaved: (paper: PaperData) => void;
  onClose: () => void;
}) {
  const [current, setCurrent] = useState(paper);
  const [values, setValues] = useState(() => draft(paper));
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [conflict, setConflict] = useState(false);
  async function save() {
    setBusy(true);
    setError("");
    try {
      const edited = {
        title: values.title.trim(),
        authors: values.authors.trim()
          ? values.authors
              .split(/[;\n]+/)
              .map((value) => value.trim())
              .filter(Boolean)
          : [],
        year: values.year ? Number(values.year) : null,
        venue: values.venue.trim() || null,
      };
      const patch: Record<string, unknown> = {
        expected_metadata_version: current.metadata_version,
      };
      for (const key of ["title", "authors", "year", "venue"] as const) {
        if (JSON.stringify(edited[key]) !== JSON.stringify(current[key]))
          patch[key] = edited[key];
      }
      const updated = await api(
        `/api/papers/${paper.id}`,
        Paper,
        patch,
        "PATCH",
      );
      onSaved(updated);
    } catch (failure) {
      const message = String(failure);
      setError(message);
      if (message.includes("paper_metadata_conflict")) setConflict(true);
    } finally {
      setBusy(false);
    }
  }
  async function reload() {
    setBusy(true);
    setError("");
    try {
      const latest = await api(`/api/papers/${paper.id}`, Paper);
      setCurrent(latest);
      setValues(draft(latest));
      setConflict(false);
    } catch (failure) {
      setError(String(failure));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form
      aria-label="编辑论文元数据"
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      <h3>编辑论文元数据</h3>
      <SourceProvenance source={current} />
      <OriginalMetadata paper={current} />
      <p>
        保存当前展示元数据；原 PDF、索引片段及来源版本保留。编辑版本：
        {current.metadata_version}。
      </p>
      <div className="grid">
        {(["title", "authors", "year", "venue"] as const).map((key) => (
          <label key={key}>
            编辑{labels[key]}
            <input
              value={values[key]}
              required={key === "title"}
              maxLength={
                key === "title"
                  ? 1000
                  : key === "authors"
                    ? 26000
                    : key === "venue"
                      ? 256
                      : undefined
              }
              type={key === "year" ? "number" : "text"}
              min={key === "year" ? 1000 : undefined}
              max={key === "year" ? 2100 : undefined}
              step={key === "year" ? 1 : undefined}
              disabled={busy}
              onChange={(event) =>
                setValues((previous) => ({
                  ...previous,
                  [key]: event.target.value,
                }))
              }
            />
          </label>
        ))}
      </div>
      <p>作者用分号分隔；空年份/会议期刊表示未记录。</p>
      {error && <p role="alert">{error}</p>}
      {conflict && (
        <p>
          当前草稿已保留。载入最新内容会替换草稿，请先保留需要的修改，再核对并重新编辑。
        </p>
      )}
      <div className="inline">
        <button type="submit" disabled={busy || conflict}>
          {busy ? "正在保存…" : "保存元数据"}
        </button>
        {conflict && (
          <button type="button" disabled={busy} onClick={() => void reload()}>
            载入最新内容并替换草稿
          </button>
        )}
        <button type="button" disabled={busy} onClick={onClose}>
          取消编辑
        </button>
      </div>
    </form>
  );
}

export function MetadataOverrides({ paper }: { paper: PaperData }) {
  return paper.overridden_fields.length ? (
    <p>
      人工维护字段：
      {paper.overridden_fields
        .map((field) => labels[field] ?? field)
        .join("、")}
    </p>
  ) : null;
}
