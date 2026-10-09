import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import { Run, api } from "./api";

const Page = z.object({
  limit: z.number(),
  offset: z.number(),
  total: z.number(),
});
const Chunks = Page.extend({
  items: z.array(
    z.object({
      chunk_id: z.string().uuid(),
      section_path: z.string(),
      page_start: z.number(),
      page_end: z.number(),
      content_sha256: z.string(),
      status: z.string(),
    }),
  ),
});
const Mention = z.object({
  id: z.string().uuid(),
  chunk_id: z.string().uuid(),
  name: z.string(),
  entity_type: z.enum(["dataset", "method", "metric"]),
  span_start: z.number(),
  span_end: z.number(),
  content_sha256: z.string(),
  state: z.enum(["proposed", "confirmed", "rejected"]),
  origin: z.string(),
  alias_group: z.string().nullable(),
  version: z.number(),
  current_source: z.boolean(),
});
const Mentions = Page.extend({ items: z.array(Mention) });
const Links = z.array(
  z.object({
    entity_id: z.string().uuid(),
    name: z.string(),
    entity_type: z.string(),
  }),
);
const Source = z.object({
  chunk_id: z.string().uuid(),
  content: z.string(),
  content_sha256: z.string().regex(/^[0-9a-f]{64}$/),
  section_path: z.string(),
  page_start: z.number(),
  page_end: z.number(),
});
const Process = z.object({
  latest_annotation_run_id: z.string().nullable().default(null),
  latest_annotation_run_status: z.string().nullable().default(null),
  latest_annotation_run_error_code: z.string().nullable().default(null),
});
const Receipt = Run.extend({
  paper_id: z.string().uuid(),
  reused_existing: z.boolean(),
  model_calls: z.literal(0),
  engine: z.literal("source-labels-v1"),
});
const Ack = z.object({ status: z.string() });
const kindLabels = { dataset: "数据集", method: "方法", metric: "指标" };
const stateLabels = {
  proposed: "待确认",
  confirmed: "已确认",
  rejected: "已拒绝",
};
const chunkLabels: Record<string, string> = {
  unprocessed: "未审阅",
  queued: "排队中",
  processing: "处理中",
  needs_review: "待人工审阅",
  completed: "审阅完成",
  failed: "失败",
};
type Span = { start: number; end: number; text: string };

export function EntityReview({
  paperId,
  onChanged,
}: {
  paperId: string;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false),
    [chunks, setChunks] = useState<z.infer<typeof Chunks> | null>(null),
    [selected, setSelected] = useState(""),
    [process, setProcess] = useState<z.infer<typeof Process> | null>(null),
    [mentions, setMentions] = useState<z.infer<typeof Mentions> | null>(null),
    [links, setLinks] = useState<z.infer<typeof Links>>([]),
    [source, setSource] = useState<z.infer<typeof Source> | null>(null);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [known, setKnown] = useState(false),
    [startAck, setStartAck] = useState(false),
    [reviewAck, setReviewAck] = useState(false),
    [removeAck, setRemoveAck] = useState(false),
    [span, setSpan] = useState<Span | null>(null),
    [kind, setKind] = useState<keyof typeof kindLabels>("dataset"),
    [editing, setEditing] = useState<z.infer<typeof Mention> | null>(null);
  const generation = useRef(0),
    controllers = useRef(new Set<AbortController>()),
    text = useRef<HTMLTextAreaElement>(null),
    changed = useRef(onChanged);
  changed.current = onChanged;
  useEffect(
    () => () => {
      generation.current++;
      controllers.current.forEach((controller) => controller.abort());
    },
    [paperId],
  );
  const current = chunks?.items.find((c) => c.chunk_id === selected);
  const running =
    process?.latest_annotation_run_status === "queued" ||
    process?.latest_annotation_run_status === "running";
  const disabled = busy || !known || running;
  async function call<T>(
    path: string,
    schema: z.ZodType<T>,
    body?: unknown,
    method?: string,
  ) {
    const controller = new AbortController();
    controllers.current.add(controller);
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      return await api(path, schema, body, method, controller.signal);
    } finally {
      clearTimeout(timer);
      controllers.current.delete(controller);
    }
  }
  function clearSource() {
    setSource(null);
    setMentions(null);
    setLinks([]);
    setSpan(null);
    setEditing(null);
    setReviewAck(false);
    setRemoveAck(false);
  }
  async function refresh(offset = chunks?.offset ?? 0) {
    const version = ++generation.current;
    setBusy(true);
    setKnown(false);
    setError("");
    try {
      const [page, state] = await Promise.all([
        call(
          `/api/papers/${paperId}/annotation-chunks?limit=50&offset=${offset}`,
          Chunks,
        ),
        call(`/api/papers/${paperId}/annotations?limit=1&offset=0`, Process),
      ]);
      if (generation.current !== version) return;
      setChunks(page);
      setProcess(state);
      setKnown(true);
      if (!page.items.some((c) => c.chunk_id === selected)) {
        setSelected(page.items[0]?.chunk_id ?? "");
        clearSource();
      } else if (
        source &&
        page.items.find((c) => c.chunk_id === selected)?.content_sha256 !==
          current?.content_sha256
      )
        clearSource();
    } catch {
      if (generation.current === version) {
        clearSource();
        setError("状态读取失败，不能确认当前来源和操作结果。请刷新后再操作。");
      }
    } finally {
      if (generation.current === version) setBusy(false);
    }
  }
  async function readSource(offset = 0) {
    if (!selected) return;
    const version = ++generation.current;
    setBusy(true);
    setKnown(false);
    setError("");
    setSpan(null);
    setEditing(null);
    try {
      const [value, page, existing, state, inventory] = await Promise.all([
        call(`/api/papers/${paperId}/chunks/${selected}/source`, Source),
        call(
          `/api/papers/${paperId}/entity-mentions?limit=50&offset=${offset}&chunk_id=${selected}`,
          Mentions,
        ),
        call(`/api/papers/${paperId}/chunks/${selected}/entities`, Links),
        call(`/api/papers/${paperId}/annotations?limit=1&offset=0`, Process),
        call(
          `/api/papers/${paperId}/annotation-chunks?limit=50&offset=${chunks?.offset ?? 0}`,
          Chunks,
        ),
      ]);
      if (generation.current !== version) return;
      setSource(value);
      setMentions(page);
      setLinks(existing);
      setProcess(state);
      setChunks({
        ...inventory,
        items: inventory.items.map((item) =>
          item.chunk_id === selected
            ? { ...item, content_sha256: value.content_sha256 }
            : item,
        ),
      });
      setKnown(true);
      setReviewAck(false);
      setRemoveAck(false);
    } catch {
      if (generation.current === version) {
        clearSource();
        setError("来源或候选读取失败，请重新读取；不能据此判断实体不存在。");
      }
    } finally {
      if (generation.current === version) setBusy(false);
    }
  }
  async function mutate(
    operation: () => Promise<unknown>,
    message: string,
    start = false,
  ) {
    const version = ++generation.current;
    setBusy(true);
    setKnown(false);
    setError("");
    setNotice("");
    let failed = false;
    try {
      await operation();
      if (generation.current !== version) return;
      setNotice(message);
    } catch {
      if (generation.current !== version) return;
      failed = true;
    }
    if (generation.current !== version) return;
    if (start) {
      clearSource();
      setStartAck(false);
      await refresh();
    } else {
      await readSource(mentions?.offset ?? 0);
    }
    if (generation.current !== version + 1) return;
    if (failed)
      setError(
        "提交失败或响应丢失。已尝试读回服务器状态，不自动重复写入；请核对当前状态、版本和原文后再操作。",
      );
    changed.current();
  }
  useEffect(() => {
    if (!open || !running || busy) return;
    const timer = setInterval(() => {
      void refresh();
    }, 3000);
    return () => clearInterval(timer);
  }, [open, running, busy, paperId]);
  function selection() {
    const node = text.current;
    if (!node || !source) return;
    // DOM offsets count UTF-16 units; backend provenance counts Unicode points.
    const start = Array.from(
        source.content.slice(0, node.selectionStart),
      ).length,
      end = Array.from(source.content.slice(0, node.selectionEnd)).length;
    const selectedText = source.content.slice(
      node.selectionStart,
      node.selectionEnd,
    );
    setSpan(end > start ? { start, end, text: selectedText } : null);
  }
  function patch(
    value: z.infer<typeof Mention>,
    action: "confirm" | "reject" | "correct",
  ) {
    if (!current) return Promise.reject(new Error("source_unknown"));
    return call(
      `/api/papers/${paperId}/entity-mentions/${value.id}`,
      Mention,
      {
        action,
        expected_version: value.version,
        expected_content_sha256: current.content_sha256,
        ...(action === "correct" && span
          ? { entity_type: kind, span_start: span.start, span_end: span.end }
          : {}),
      },
      "PATCH",
    );
  }
  return (
    <details
      aria-label="实体提取与人工校正"
      onToggle={(event) => {
        if (event.target !== event.currentTarget) return;
        const expanded = event.currentTarget.open;
        setOpen(expanded);
        if (expanded) void refresh();
        else {
          generation.current++;
          controllers.current.forEach((controller) => controller.abort());
          setKnown(false);
          setBusy(false);
          clearSource();
        }
      }}
    >
      <summary>生成实体候选与人工校正</summary>
      {open && (
        <>
          <p>
            本地规则识别明确标签及紧邻实体类型词的名称，不调用模型（0
            次模型调用）。覆盖有限；候选经你确认后才加入严格过滤索引。旧实体链接需另行核对，未识别不代表不存在。
          </p>
          <button disabled={busy} onClick={() => void refresh()}>
            读取最新标注任务与片段
          </button>
          {busy && <p role="status">正在读取或保存，请等待服务器确认…</p>}
          {error && <p role="alert">{error}</p>}
          {notice && <p role="status">{notice}</p>}
          {process?.latest_annotation_run_id && (
            <p>
              最近提取任务：{process.latest_annotation_run_status} ·{" "}
              {process.latest_annotation_run_id}
              {process.latest_annotation_run_error_code &&
                " · 执行或派发失败，请检查任务服务并显式重试；旧结果保留。"}
            </p>
          )}
          <label className="entity-check">
            <input
              type="checkbox"
              checked={startAck}
              disabled={disabled}
              onChange={(event) => setStartAck(event.target.checked)}
            />
            我会核对候选，不把未确认候选当作科研事实
          </label>
          <button
            disabled={disabled || !startAck}
            onClick={() =>
              void mutate(
                () =>
                  call(
                    `/api/papers/${paperId}/annotation-runs`,
                    Receipt,
                    {
                      engine: "source-labels-v1",
                      acknowledge_candidates_require_review: true,
                    },
                    "POST",
                  ),
                "提取请求已由服务器接收；提取完成仍需人工审阅。",
                true,
              )
            }
          >
            生成或重试本地实体候选
          </button>
          {running && (
            <p role="status">
              提取任务进行中，人工修改暂不可用；会自动读取进度。
            </p>
          )}
          {chunks && (
            <>
              <label>
                待审阅片段
                <select
                  aria-label="待审阅片段"
                  disabled={busy}
                  value={selected}
                  onChange={(event) => {
                    setSelected(event.target.value);
                    clearSource();
                  }}
                >
                  {chunks.items.map((c, i) => (
                    <option key={c.chunk_id} value={c.chunk_id}>
                      #{chunks.offset + i + 1} · {c.section_path} · p.
                      {c.page_start}–{c.page_end} ·{" "}
                      {chunkLabels[c.status] ?? c.status}
                    </option>
                  ))}
                </select>
              </label>
              <p>
                当前页 {chunks.items.length} / 共 {chunks.total} 个片段
              </p>
              <button
                disabled={busy || chunks.offset === 0}
                onClick={() => void refresh(Math.max(0, chunks.offset - 50))}
              >
                上一页审阅片段
              </button>
              <button
                disabled={busy || chunks.offset + chunks.limit >= chunks.total}
                onClick={() => void refresh(chunks.offset + 50)}
              >
                下一页审阅片段
              </button>
              <button
                disabled={busy || !known || !selected}
                onClick={() => void readSource()}
              >
                读取当前片段与候选
              </button>
            </>
          )}
          {source && current && (
            <>
              <p>
                {source.section_path} · p.{source.page_start}–{source.page_end}{" "}
                · 原文只读。选择连续的完整实体名称，再选择类型。
              </p>
              <textarea
                ref={text}
                className="entity-source"
                aria-label="用于实体核对的原文"
                readOnly
                value={source.content}
                onSelect={selection}
              />
              <p aria-label="已选择实体原文">
                {span ? `已选：${span.text}` : "尚未选择实体原文"}
              </p>
              <label>
                实体类型
                <select
                  aria-label="实体类型"
                  disabled={disabled}
                  value={kind}
                  onChange={(event) =>
                    setKind(event.target.value as keyof typeof kindLabels)
                  }
                >
                  {Object.entries(kindLabels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <button
                disabled={
                  disabled ||
                  !span ||
                  Array.from(span.text).length > 256 ||
                  editing !== null
                }
                onClick={() =>
                  void mutate(
                    () =>
                      call(
                        `/api/papers/${paperId}/chunks/${selected}/entity-mentions`,
                        Mention,
                        {
                          entity_type: kind,
                          span_start: span!.start,
                          span_end: span!.end,
                          expected_content_sha256: current.content_sha256,
                        },
                        "POST",
                      ),
                    "人工候选已保存，仍需单独确认。",
                  )
                }
              >
                保存选中原文为人工候选
              </button>
              {editing && (
                <div role="group" aria-label="修改实体候选">
                  <p>
                    修改 {editing.name}：重新选择原文与类型，保存后仍待确认。
                  </p>
                  <button
                    disabled={disabled || !span}
                    onClick={() =>
                      void mutate(
                        () => patch(editing, "correct"),
                        "修改已保存，仍待确认。",
                      )
                    }
                  >
                    保存实体修改
                  </button>
                  <button
                    disabled={busy}
                    onClick={() => {
                      setEditing(null);
                      setSpan(null);
                    }}
                  >
                    取消实体修改
                  </button>
                </div>
              )}
              {mentions && (
                <>
                  <p>
                    本片段共 {mentions.total}{" "}
                    条候选记录；拒绝记录保留，不会自动复活。
                  </p>
                  <ul>
                    {mentions.items.map((value) => (
                      <li key={value.id}>
                        <strong>
                          {kindLabels[value.entity_type]}：{value.name}
                        </strong>{" "}
                        · {stateLabels[value.state]}
                        {!value.current_source && " · 原文已变化，请重新核对"}
                        {value.alias_group && (
                          <p>
                            原文括号候选关联，需分别确认；不跨论文猜测或合并同义词。
                          </p>
                        )}
                        <p>
                          原文跨度：{value.span_start}–{value.span_end}
                        </p>
                        <button
                          disabled={
                            disabled ||
                            !value.current_source ||
                            value.state === "confirmed"
                          }
                          onClick={() =>
                            void mutate(
                              () => patch(value, "confirm"),
                              "实体已人工确认，可用于严格过滤；不代表已审阅全部片段。",
                            )
                          }
                        >
                          确认 {value.name}
                        </button>
                        <button
                          disabled={disabled || value.state === "rejected"}
                          onClick={() =>
                            void mutate(
                              () => patch(value, "reject"),
                              "此候选已拒绝；其他片段与论文不变。",
                            )
                          }
                        >
                          拒绝 {value.name}
                        </button>
                        <button
                          disabled={disabled || !value.current_source}
                          onClick={() => {
                            setEditing(value);
                            setSpan(null);
                            setKind(value.entity_type);
                          }}
                        >
                          修改 {value.name}
                        </button>
                      </li>
                    ))}
                  </ul>
                  <button
                    disabled={busy || mentions.offset === 0}
                    onClick={() =>
                      void readSource(Math.max(0, mentions.offset - 50))
                    }
                  >
                    上一页候选
                  </button>
                  <button
                    disabled={
                      busy || mentions.offset + mentions.limit >= mentions.total
                    }
                    onClick={() => void readSource(mentions.offset + 50)}
                  >
                    下一页候选
                  </button>
                </>
              )}
              <details>
                <summary>核对和移除当前实体链接</summary>
                <p>
                  现有链接可能来自旧流程、未记录精确跨度。移除仅作用当前片段，原文和共享名称保留。
                </p>
                <label className="entity-check">
                  <input
                    type="checkbox"
                    checked={removeAck}
                    disabled={disabled}
                    onChange={(event) => setRemoveAck(event.target.checked)}
                  />
                  我确认只移除当前片段的实体链接
                </label>
                <ul>
                  {links.map((link) => (
                    <li key={link.entity_id}>
                      {link.name}
                      <button
                        disabled={disabled || !removeAck}
                        onClick={() =>
                          void mutate(
                            () =>
                              call(
                                `/api/papers/${paperId}/chunks/${selected}/entities/${link.entity_id}`,
                                Ack,
                                {
                                  expected_content_sha256:
                                    current.content_sha256,
                                  acknowledge_remove_link: true,
                                },
                                "DELETE",
                              ),
                            "当前片段的实体链接已移除。",
                          )
                        }
                      >
                        移除 {link.name} 链接
                      </button>
                    </li>
                  ))}
                </ul>
              </details>
              <label className="entity-check">
                <input
                  type="checkbox"
                  disabled={disabled}
                  checked={reviewAck}
                  onChange={(event) => setReviewAck(event.target.checked)}
                />
                我已核对整个片段的数据集、方法和指标，并处理所有候选
              </label>
              <button
                disabled={
                  disabled ||
                  !reviewAck ||
                  mentions === null ||
                  mentions.items.some(
                    (value) =>
                      value.current_source && value.state === "proposed",
                  )
                }
                onClick={() =>
                  void mutate(
                    () =>
                      call(
                        `/api/papers/${paperId}/chunks/${selected}/annotation-review`,
                        Ack,
                        {
                          expected_content_sha256: current.content_sha256,
                          acknowledge_all_three_types_reviewed: true,
                        },
                        "POST",
                      ),
                    "当前片段审阅完成；其他片段仍需逐一核对。",
                  )
                }
              >
                确认整个片段审阅完成
              </button>
            </>
          )}
        </>
      )}
    </details>
  );
}
