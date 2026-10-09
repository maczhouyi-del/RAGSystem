import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import { Paper, PaperPage, Run, api } from "./api";
import type { SourceStatus } from "./api";
import { PaperAnnotations } from "./Annotations";
import { PdfImports } from "./PdfImports";
import {
  CollectionManager,
  CollectionOptions,
  PaperOrganization,
  useCollections,
} from "./Collections";
import { isDesktop, openPaperPdf } from "./transport";
import { SourceProvenance, sourceStatusLabels } from "./components";
import {
  MetadataOverrides,
  OriginalMetadata,
  PaperMetadataEditor,
} from "./PaperMetadataEditor";
import {
  PaperDeletionDialog,
  PaperDeletionStatus,
  usePaperDeletions,
} from "./PaperDeletion";
const pageSize = 50;
const initialFilters = {
  title: "",
  author: "",
  year: "",
  venue: "",
  status: "",
  group: "",
  tag: "",
  sort: "created_at",
  direction: "desc",
};
export function Knowledge() {
  const catalog = useCollections();
  const [papers, setPapers] = useState<z.infer<typeof Paper>[]>([]),
    [error, setError] = useState(""),
    [arxiv, setArxiv] = useState(""),
    [busy, setBusy] = useState(false),
    [task, setTask] = useState(""),
    [filters, setFilters] = useState(initialFilters),
    [query, setQuery] = useState({ ...initialFilters, offset: 0 }),
    [total, setTotal] = useState<number | null>(null),
    [loading, setLoading] = useState(false),
    [sourceEdits, setSourceEdits] = useState<Record<string, SourceStatus>>({}),
    [savingPaper, setSavingPaper] = useState<string | null>(null),
    [sourceNotice, setSourceNotice] = useState("");
  const [editingPaper, setEditingPaper] = useState<z.infer<
    typeof Paper
  > | null>(null);
  const [deletingPaper, setDeletingPaper] = useState<z.infer<
    typeof Paper
  > | null>(null);
  const requestSequence = useRef(0);
  const removedIds = useRef(new Set<string>());
  const deletions = usePaperDeletions((id) => {
    removedIds.current.add(id);
    setPapers((items) => items.filter((item) => item.id !== id));
    setSourceEdits((edits) => {
      const remaining = { ...edits };
      delete remaining[id];
      return remaining;
    });
    void refresh();
  });
  const offset = query.offset;
  const hasNext = total !== null && offset + pageSize < total;
  const setOffset = (value: number) =>
    setQuery((current) => ({ ...current, offset: value }));
  async function refresh(pageOffset = offset, signal?: AbortSignal) {
    const sequence = ++requestSequence.current;
    setLoading(true);
    try {
      const parameters = new URLSearchParams({
        limit: String(pageSize),
        offset: String(pageOffset),
      });
      for (const [key, value] of Object.entries(query)) {
        if (key !== "offset" && String(value).trim())
          parameters.set(key, String(value).trim());
      }
      const page = await api(
        `/api/papers/search?${parameters}`,
        PaperPage,
        undefined,
        "GET",
        signal,
      );
      if (signal?.aborted || sequence !== requestSequence.current) return;
      if (pageOffset > 0 && pageOffset >= page.total) {
        setOffset(
          page.total ? Math.floor((page.total - 1) / pageSize) * pageSize : 0,
        );
        return;
      }
      setPapers(
        page.items.filter((paper) => !removedIds.current.has(paper.id)),
      );
      setTotal(page.total);
      setError("");
    } catch (e) {
      if (!signal?.aborted && sequence === requestSequence.current)
        setError(String(e));
    } finally {
      if (!signal?.aborted && sequence === requestSequence.current)
        setLoading(false);
    }
  }
  useEffect(() => {
    const controller = new AbortController();
    void refresh(offset, controller.signal);
    const i = setInterval(() => void refresh(offset, controller.signal), 5000);
    return () => {
      clearInterval(i);
      controller.abort();
    };
  }, [query]);
  async function importArxiv() {
    setBusy(true);
    setError("");
    try {
      const r = await api("/api/papers/arxiv", Run, { arxiv_id: arxiv });
      setTask(r.id);
      if (offset) setOffset(0);
      else await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function saveSourceStatus(paper: z.infer<typeof Paper>) {
    setSavingPaper(paper.id);
    setError("");
    setSourceNotice("");
    try {
      const updated = await api(
        `/api/papers/${paper.id}`,
        Paper,
        {
          source_status: sourceEdits[paper.id] ?? paper.source_status,
          expected_metadata_version: paper.metadata_version,
        },
        "PATCH",
      );
      setPapers((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
      setSourceEdits((edits) => {
        const remaining = { ...edits };
        delete remaining[paper.id];
        return remaining;
      });
      setSourceNotice(`${updated.title}：来源状态已保存`);
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setSavingPaper(null);
    }
  }
  return (
    <section>
      <h2>Knowledge Base</h2>
      <PdfImports
        onAccepted={() => {
          if (offset) setOffset(0);
          else void refresh();
        }}
      />
      <div className="inline">
        <input
          aria-label="arXiv ID"
          value={arxiv}
          onChange={(e) => setArxiv(e.target.value)}
          placeholder="arXiv ID，如 2408.09869"
        />
        <button disabled={busy || !arxiv} onClick={() => void importArxiv()}>
          导入开放论文
        </button>
      </div>
      {task && <p>后台任务：{task}。首次解析和模型加载可能需要数分钟。</p>}
      {error && <p role="alert">{error}</p>}
      {sourceNotice && <p role="status">{sourceNotice}</p>}
      <PaperDeletionStatus manager={deletions} />
      <CollectionManager catalog={catalog} onChanged={() => void refresh()} />
      {deletingPaper && (
        <PaperDeletionDialog
          key={deletingPaper.id}
          paper={deletingPaper}
          onClose={() => setDeletingPaper(null)}
          onTracked={deletions.track}
        />
      )}
      <p>
        来源状态需人工核对；indexed 仅表示已建立索引，不代表来源状态已核验。
      </p>
      <form
        aria-label="文献搜索与筛选"
        onSubmit={(event) => {
          event.preventDefault();
          setQuery({ ...filters, offset: 0 });
        }}
      >
        <div className="grid">
          {(["group", "tag"] as const).map((kind) => (
            <label key={kind}>
              {kind === "group" ? "筛选论文分组" : "筛选自定义标签"}
              <select
                value={filters[kind]}
                onFocus={() => void catalog.load()}
                onChange={(event) =>
                  setFilters((current) => ({
                    ...current,
                    [kind]: event.target.value,
                  }))
                }
              >
                <option value="">
                  {kind === "group" ? "全部分组" : "全部标签"}
                </option>
                <CollectionOptions
                  items={catalog.items}
                  kind={kind}
                  selected={[filters[kind]].filter(Boolean)}
                />
              </select>
            </label>
          ))}
          {(
            [
              ["title", "搜索论文标题", 1000],
              ["author", "搜索作者", 256],
              ["venue", "筛选会议或期刊", 256],
            ] as const
          ).map(([key, label, maxLength]) => (
            <label key={key}>
              {label}
              <input
                value={filters[key]}
                maxLength={maxLength}
                onChange={(event) =>
                  setFilters((current) => ({
                    ...current,
                    [key]: event.target.value,
                  }))
                }
              />
            </label>
          ))}
          <label>
            筛选论文年份
            <input
              type="number"
              min="1000"
              max="2100"
              step="1"
              value={filters.year}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  year: event.target.value,
                }))
              }
            />
          </label>
          <label>
            筛选索引状态
            <select
              aria-label="筛选索引状态"
              value={filters.status}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  status: event.target.value,
                }))
              }
            >
              <option value="">全部状态</option>
              <option value="queued">等待索引</option>
              <option value="parsing">解析中</option>
              <option value="indexing">索引中</option>
              <option value="indexed">已建立索引</option>
              <option value="failed">索引失败</option>
            </select>
          </label>
          <label>
            文献排序字段
            <select
              aria-label="文献排序字段"
              value={filters.sort}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  sort: event.target.value,
                }))
              }
            >
              <option value="created_at">创建时间</option>
              <option value="year">论文年份</option>
            </select>
          </label>
          <label>
            文献排序方向
            <select
              aria-label="文献排序方向"
              value={filters.direction}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  direction: event.target.value,
                }))
              }
            >
              <option value="desc">从新到旧</option>
              <option value="asc">从旧到新</option>
            </select>
          </label>
        </div>
        <div className="inline">
          <button type="submit">搜索文献</button>
          <button
            type="button"
            onClick={() => {
              setFilters(initialFilters);
              setQuery({ ...initialFilters, offset: 0 });
            }}
          >
            清除筛选
          </button>
        </div>
      </form>
      <div className="inline" aria-label="文献分页">
        <button disabled={loading} onClick={() => void refresh()}>
          刷新
        </button>
        <button
          disabled={loading || offset === 0}
          onClick={() => setOffset(Math.max(0, offset - pageSize))}
        >
          上一页
        </button>
        <button
          disabled={loading || !hasNext}
          onClick={() => setOffset(offset + pageSize)}
        >
          下一页
        </button>
        <p role="status">
          {loading
            ? "正在查询文献…"
            : total === null
              ? "总数未知"
              : `共 ${total} 篇 · 第 ${offset / pageSize + 1} / ${Math.max(1, Math.ceil(total / pageSize))} 页`}
        </p>
      </div>
      {editingPaper && (
        <PaperMetadataEditor
          key={editingPaper.id}
          paper={editingPaper}
          onClose={() => setEditingPaper(null)}
          onSaved={(updated) => {
            setPapers((items) =>
              items.map((item) => (item.id === updated.id ? updated : item)),
            );
            setEditingPaper(null);
            setSourceNotice(`${updated.title}：元数据已保存`);
            void refresh();
          }}
        />
      )}
      <table aria-busy={loading}>
        <thead>
          <tr>
            <th>论文</th>
            <th>元数据</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          {papers.map((p) => (
            <tr key={p.id}>
              <td>
                <a
                  href={`/api/papers/${p.id}/pdf`}
                  onClick={(event) => {
                    if (isDesktop()) {
                      event.preventDefault();
                      void openPaperPdf(p.id).catch((e) => setError(String(e)));
                    }
                  }}
                  target="_blank"
                  rel="noreferrer"
                >
                  {p.title}
                </a>
                <small>{p.id}</small>
                <SourceProvenance source={p} />
              </td>
              <td>
                {p.authors.join("; ")}
                <br />
                {p.year} · {p.venue}
                <MetadataOverrides paper={p} />
                <PaperAnnotations paperId={p.id} title={p.title} />
                <OriginalMetadata paper={p} />
                <PaperOrganization
                  paper={p}
                  catalog={catalog}
                  disabled={deletingPaper !== null || editingPaper !== null}
                  onChanged={() => void refresh()}
                />
                <button
                  aria-label={`编辑 ${p.title} 元数据`}
                  disabled={
                    editingPaper !== null ||
                    deletingPaper !== null ||
                    savingPaper !== null
                  }
                  onClick={() => setEditingPaper(p)}
                >
                  编辑元数据
                </button>
                <label>
                  来源状态（人工核对）
                  <select
                    aria-label={`${p.title} 来源状态`}
                    value={sourceEdits[p.id] ?? p.source_status}
                    disabled={savingPaper === p.id || deletingPaper !== null}
                    onChange={(event) =>
                      setSourceEdits((edits) => ({
                        ...edits,
                        [p.id]: event.target.value as SourceStatus,
                      }))
                    }
                  >
                    {Object.entries(sourceStatusLabels).map(
                      ([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ),
                    )}
                  </select>
                </label>
                <button
                  aria-label={`保存 ${p.title} 来源状态`}
                  disabled={
                    savingPaper !== null ||
                    deletingPaper !== null ||
                    sourceEdits[p.id] === undefined ||
                    sourceEdits[p.id] === p.source_status
                  }
                  onClick={() => void saveSourceStatus(p)}
                >
                  {savingPaper === p.id ? "正在保存…" : "保存来源状态"}
                </button>
              </td>
              <td>
                {p.status} · {p.chunk_count} chunks
                {p.error_code && <span role="alert">{p.error_code}</span>}
                <button
                  aria-label={`删除 ${p.title}`}
                  className="danger"
                  disabled={
                    deletingPaper !== null ||
                    editingPaper !== null ||
                    savingPaper !== null
                  }
                  onClick={() => setDeletingPaper(p)}
                >
                  删除文献
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!loading && !error && !papers.length && (
        <p>
          {Object.entries(query).some(
            ([key, value]) =>
              !["offset", "sort", "direction"].includes(key) && value,
          )
            ? "没有符合筛选条件的文献。可清除筛选后重试。"
            : "知识库为空。先上传 PDF 或导入 arXiv 论文。"}
        </p>
      )}
    </section>
  );
}
