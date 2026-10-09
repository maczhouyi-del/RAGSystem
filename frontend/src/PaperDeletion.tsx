import { useCallback, useEffect, useRef, useState } from "react";
import { z } from "zod";
import { Paper, PaperDeletion, PaperDeletionPreview, api } from "./api";
import { SourceProvenance } from "./components";
import { errorMessage } from "./errors";

const storageKey = "ragagent-paper-deletion-status-ids-v1";
const rememberedIds = z.array(z.string().uuid()).max(20);
function readIds(): string[] {
  try {
    const parsed = rememberedIds.safeParse(
      JSON.parse(localStorage.getItem(storageKey) ?? "[]"),
    );
    return parsed.success ? [...new Set(parsed.data)] : [];
  } catch {
    return [];
  }
}
function writeIds(ids: string[]) {
  try {
    localStorage.setItem(storageKey, JSON.stringify(ids.slice(-20)));
  } catch {
    // The authoritative ledger remains on the server. Never store a mutation body.
  }
}
function remember(id: string) {
  const ids = [...readIds().filter((value) => value !== id), id].slice(-20);
  writeIds(ids);
  return ids;
}
function forget(id: string) {
  const ids = readIds().filter((value) => value !== id);
  writeIds(ids);
  return ids;
}

const copyLabels: Record<string, string> = {
  desktop_documents_cache:
    "桌面应用的 documents PDF 缓存（关闭阅读器后自行清理）",
  external_pdf_reader: "操作系统或外部 PDF 阅读器中的副本",
  downloaded_exports: "已下载的报告和导出",
  user_saved_files: "用户另存的 PDF 与其他文件",
  backups_and_sync: "备份与同步副本（恢复旧备份后须重新应用删除记录）",
  external_provider_retention: "外部模型服务的留存（按服务商规则管理）",
  conversation_answer_prose: "历史回答、问题和摘要正文（可能仍含来源内容）",
};
export function RetainedCopies({ copies }: { copies: string[] }) {
  return (
    <aside className="retained-copies" aria-label="仍需自行管理的副本">
      <strong>仅移除当前知识库，不保证全部副本抹除</strong>
      <ul>
        {copies.map((copy) => (
          <li key={copy}>{copyLabels[copy] ?? "其他独立副本，需自行核对"}</li>
        ))}
      </ul>
      <p>
        本操作不会清空其他会话、其他文献或共享模型。请明确选择自己的文件再清理。
      </p>
    </aside>
  );
}

type Entry = {
  status?: PaperDeletion;
  error?: string;
  requestError?: string;
  retrying?: boolean;
};
/** Bounded IDs support read-only recovery. The server owns every job and retry. */
export function usePaperDeletions(onRemoved: (id: string) => void) {
  const [ids, setIds] = useState(readIds);
  const [entries, setEntries] = useState<Record<string, Entry>>({});
  const alive = useRef(true);
  const current = useRef(entries);
  current.current = entries;
  const callback = useRef(onRemoved);
  callback.current = onRemoved;
  const sequences = useRef<Record<string, number>>({});
  const reading = useRef(new Set<string>());
  const mutating = useRef(new Set<string>());
  const notified = useRef(new Set<string>());
  const accept = useCallback((id: string, status: PaperDeletion) => {
    if (status.paper_id !== id)
      throw new Error(errorMessage("invalid_response"));
    if (!alive.current) return;
    setEntries((previous) => ({ ...previous, [id]: { status } }));
    if (!notified.current.has(id)) {
      notified.current.add(id);
      callback.current(id);
    }
  }, []);
  const refresh = useCallback(
    async (id: string) => {
      if (reading.current.has(id) || mutating.current.has(id)) return;
      const sequence = (sequences.current[id] ?? 0) + 1;
      sequences.current[id] = sequence;
      reading.current.add(id);
      try {
        const status = await api(
          `/api/papers/${id}/deletion`,
          PaperDeletion,
          undefined,
          "GET",
          AbortSignal.timeout(10000),
        );
        if (sequences.current[id] === sequence) accept(id, status);
      } catch (failure) {
        if (alive.current && sequences.current[id] === sequence)
          setEntries((previous) => ({
            ...previous,
            [id]: { ...previous[id], error: String(failure) },
          }));
      } finally {
        reading.current.delete(id);
      }
    },
    [accept],
  );
  const track = useCallback(
    (id: string, status?: PaperDeletion, requestError?: string) => {
      if (!alive.current) return;
      setIds(remember(id));
      if (requestError)
        setEntries((previous) => ({
          ...previous,
          [id]: { ...previous[id], requestError },
        }));
      if (status) accept(id, status);
      else void refresh(id);
    },
    [accept, refresh],
  );
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    for (const id of ids) void refresh(id);
    const pending = () => {
      if (document.visibilityState === "hidden") return;
      for (const id of ids) {
        const state = current.current[id]?.status?.cleanup_status;
        if (!state || state === "queued" || state === "running")
          void refresh(id);
      }
    };
    const timer = setInterval(pending, 5000);
    window.addEventListener("focus", pending);
    window.addEventListener("online", pending);
    document.addEventListener("visibilitychange", pending);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", pending);
      window.removeEventListener("online", pending);
      document.removeEventListener("visibilitychange", pending);
    };
  }, [ids, refresh]);
  const retry = async (id: string) => {
    const state = current.current[id]?.status?.cleanup_status;
    if (
      mutating.current.has(id) ||
      !state ||
      !["queued", "failed", "cancelled"].includes(state)
    )
      return;
    mutating.current.add(id);
    sequences.current[id] = (sequences.current[id] ?? 0) + 1;
    setEntries((previous) => ({
      ...previous,
      [id]: { ...previous[id], retrying: true, error: "" },
    }));
    try {
      accept(
        id,
        await api(
          `/api/papers/${id}/deletion/retry`,
          PaperDeletion,
          {},
          "POST",
          AbortSignal.timeout(30000),
        ),
      );
    } catch (failure) {
      if (alive.current)
        setEntries((previous) => ({
          ...previous,
          [id]: { error: `重试结果待核对。${String(failure)}` },
        }));
    } finally {
      mutating.current.delete(id);
      if (alive.current) void refresh(id);
    }
  };
  return {
    ids,
    entries,
    track,
    refresh,
    retry,
    dismiss: (id: string) => {
      setIds(forget(id));
      sequences.current[id] = (sequences.current[id] ?? 0) + 1;
    },
  };
}

const cleanupLabels = {
  queued: "等待清理",
  running: "正在清理",
  completed: "受管文件清理完成",
  failed: "清理失败",
  cancelled: "清理已中断",
};
export function PaperDeletionStatus({
  manager,
}: {
  manager: ReturnType<typeof usePaperDeletions>;
}) {
  return (
    <div aria-label="文献删除状态">
      {manager.ids.map((id) => {
        const entry = manager.entries[id];
        const status = entry?.status;
        return (
          <section
            key={id}
            className="paper-deletion-status"
            aria-label={`删除状态 ${id}`}
          >
            <h3>{status ? "已移出当前知识库" : "删除结果待核对"}</h3>
            <small>文献：{id}</small>
            {status ? (
              <>
                <p role="status">
                  {cleanupLabels[status.cleanup_status]} · 清理任务：
                  {status.cleanup_run_id}
                </p>
                <p>
                  新检索已排除此来源；历史引用当前不可验证。文件清理失败也不会恢复文献。
                </p>
                {status.error_code && (
                  <p role="alert">{errorMessage(status.error_code)}</p>
                )}
                {status.retained_managed_files.length > 0 && (
                  <p>
                    另有受管文件已保留：
                    {status.retained_managed_files
                      .map((reason) =>
                        reason === "shared_by_other_paper"
                          ? "其他论文仍在使用"
                          : "路径未纳入受管目录",
                      )
                      .join("；")}
                    。
                  </p>
                )}
                <RetainedCopies copies={status.retained_copies} />
                {["queued", "failed", "cancelled"].includes(
                  status.cleanup_status,
                ) && (
                  <button
                    disabled={entry?.retrying}
                    onClick={() => void manager.retry(id)}
                  >
                    {entry?.retrying
                      ? "正在提交清理重试…"
                      : "重试清理文件与队列"}
                  </button>
                )}
              </>
            ) : (
              <p>
                请求可能已在后端提交。请读取删除记录确认结果；不会自动再次删除。重载后只恢复状态查询。
              </p>
            )}
            {(entry?.requestError || entry?.error) && (
              <p role="alert">
                {entry.requestError} {entry.error}
              </p>
            )}
            <button
              disabled={entry?.retrying}
              onClick={() => void manager.refresh(id)}
            >
              读取最新删除状态
            </button>
            {(!status ||
              ["completed", "failed", "cancelled"].includes(
                status.cleanup_status,
              )) && (
              <button onClick={() => manager.dismiss(id)}>关闭状态提示</button>
            )}
          </section>
        );
      })}
    </div>
  );
}

export function PaperDeletionDialog({
  paper,
  onClose,
  onTracked,
}: {
  paper: z.infer<typeof Paper>;
  onClose: () => void;
  onTracked: (
    id: string,
    status?: PaperDeletion,
    requestError?: string,
  ) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const alive = useRef(true);
  const previewController = useRef<AbortController | null>(null);
  const [latest, setLatest] = useState(paper);
  const [preview, setPreview] = useState<z.infer<
    typeof PaperDeletionPreview
  > | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [error, setError] = useState("");
  async function loadPreview() {
    previewController.current?.abort();
    const controller = new AbortController();
    previewController.current = controller;
    const timeout = setTimeout(() => controller.abort(), 10000);
    setLoading(true);
    setPreview(null);
    setAcknowledged(false);
    setError("");
    try {
      const [fresh, next] = await Promise.all([
        api(
          `/api/papers/${paper.id}`,
          Paper,
          undefined,
          "GET",
          controller.signal,
        ),
        api(
          `/api/papers/${paper.id}/deletion-preview`,
          PaperDeletionPreview,
          undefined,
          "GET",
          controller.signal,
        ),
      ]);
      if (!alive.current || controller.signal.aborted) return;
      if (
        fresh.id !== paper.id ||
        next.paper_id !== paper.id ||
        fresh.metadata_version !== next.metadata_version
      )
        throw new Error("文献信息在读取期间变化，请重新读取预览并核对。");
      setLatest(fresh);
      setPreview(next);
    } catch (failure) {
      if (alive.current && previewController.current === controller)
        setError(
          controller.signal.aborted
            ? "预览读取超时，请检查本机服务后重试。"
            : String(failure),
        );
    } finally {
      clearTimeout(timeout);
      if (alive.current && previewController.current === controller)
        setLoading(false);
    }
  }
  useEffect(() => {
    alive.current = true;
    dialog.current?.showModal();
    void loadPreview();
    return () => {
      alive.current = false;
      previewController.current?.abort();
      dialog.current?.close();
    };
  }, []);
  async function submit() {
    if (!preview || !acknowledged || submitting) return;
    setSubmitting(true);
    setError("");
    const wasRemembered = readIds().includes(paper.id);
    remember(paper.id); // Persist only an ID before a potentially ambiguous request.
    try {
      const status = await api(
        `/api/papers/${paper.id}`,
        PaperDeletion,
        {
          confirm_paper_id: paper.id,
          expected_metadata_version: preview.metadata_version,
          scope: "current_library",
          acknowledge_retained_copies: true,
        },
        "DELETE",
        AbortSignal.timeout(30000),
      );
      if (status.paper_id !== paper.id)
        throw new Error(errorMessage("invalid_response"));
      if (alive.current) {
        onTracked(paper.id, status);
        onClose();
      }
    } catch (failure) {
      if (!alive.current) return;
      if (
        String(failure).includes("paper_metadata_conflict") ||
        String(failure).includes("paper_deletion_confirmation_mismatch")
      ) {
        if (!wasRemembered) forget(paper.id);
        setAcknowledged(false);
        setPreview(null);
        setError("文献信息已有更新，本次未删除。请重新读取预览、核对并确认。");
      } else {
        onTracked(paper.id, undefined, String(failure));
        onClose();
      }
    } finally {
      if (alive.current) setSubmitting(false);
    }
  }
  return (
    <dialog
      ref={dialog}
      className="paper-deletion-dialog"
      aria-label="确认删除文献"
      onCancel={(event) => {
        event.preventDefault();
        if (!submitting) onClose();
      }}
    >
      <div className="deletion-content">
        <h3>从当前知识库删除这篇文献？</h3>
        <strong>{latest.title}</strong>
        <small>{paper.id}</small>
        <SourceProvenance source={latest} />
        <p>
          将移除论文与索引、结构化证据和实体关联，并停止相关导入和实体提取任务。历史回答正文保留，引用标记为来源不可用。此操作不能撤销；重新导入会创建新的来源身份。
        </p>
        {loading && <p role="status">正在读取删除范围…</p>}
        {preview && (
          <>
            <p>
              元数据版本：{preview.metadata_version}；涉及 {preview.chunks}{" "}
              个文本块、{preview.evidence} 条证据、{preview.pending_imports}{" "}
              个未完成来源处理任务（含导入与实体提取）。
            </p>
            <RetainedCopies copies={preview.retained_copies} />
            <label className="deletion-acknowledgement">
              <input
                type="checkbox"
                checked={acknowledged}
                disabled={submitting}
                onChange={(event) => setAcknowledged(event.target.checked)}
              />
              我已核对文献，并了解独立副本和历史正文仍需自行管理
            </label>
          </>
        )}
        {error && <p role="alert">{error}</p>}
        {!preview && !loading && (
          <button disabled={submitting} onClick={() => void loadPreview()}>
            重新读取删除预览
          </button>
        )}
      </div>
      <div className="inline">
        <button autoFocus disabled={submitting} onClick={onClose}>
          取消删除
        </button>
        <button
          className="danger"
          disabled={!preview || !acknowledged || loading || submitting}
          onClick={() => void submit()}
        >
          {submitting ? "正在提交删除，请勿重复操作…" : "确认移出知识库"}
        </button>
      </div>
    </dialog>
  );
}
