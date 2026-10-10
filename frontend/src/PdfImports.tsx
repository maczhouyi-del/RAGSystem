import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import { Paper, Run, UploadReceipt, api } from "./api";
import { errorMessage } from "./errors";
import { isDesktop, openPaperPdf } from "./transport";

const uploadConcurrency = 2,
  statusConcurrency = 4,
  selectionLimit = 100;
const maxFileBytes = 30 * 1024 * 1024;
const storageKey = "ragagent-import-status-ids-v1";
const Stored = z
  .array(z.object({ paper_id: z.string().uuid(), run_id: z.string().uuid() }))
  .max(50);
type Metadata = { title: string; authors: string; year: string; venue: string };
type Stage =
  | "waiting"
  | "uploading"
  | "processing"
  | "indexed"
  | "upload_failed"
  | "index_failed"
  | "unavailable";
type Row = {
  id: string;
  name: string;
  stage: Stage;
  file?: File;
  metadata?: Metadata;
  paperId?: string;
  runId?: string;
  paper?: z.infer<typeof Paper>;
  run?: Run;
  reused?: boolean;
  error?: string;
  uncertain?: boolean;
  retrying?: boolean;
};
function restore(): Row[] {
  try {
    const parsed = Stored.safeParse(
      JSON.parse(localStorage.getItem(storageKey) ?? "[]"),
    );
    return parsed.success
      ? parsed.data.map((entry) => ({
          id: crypto.randomUUID(),
          name: entry.paper_id,
          paperId: entry.paper_id,
          runId: entry.run_id,
          stage: "processing",
        }))
      : [];
  } catch {
    return [];
  }
}
function persist(rows: Row[]) {
  const byPaper = new Map<string, { paper_id: string; run_id: string }>();
  for (const row of rows) {
    if (
      row.paperId &&
      row.runId &&
      z.string().uuid().safeParse(row.paperId).success &&
      z.string().uuid().safeParse(row.runId).success
    )
      byPaper.set(row.paperId, { paper_id: row.paperId, run_id: row.runId });
  }
  try {
    localStorage.setItem(
      storageKey,
      JSON.stringify([...byPaper.values()].slice(-50)),
    );
  } catch {
    /* Server jobs remain authoritative. */
  }
}
async function bounded<T>(items: T[], action: (item: T) => Promise<void>) {
  let next = 0;
  await Promise.all(
    Array.from(
      { length: Math.min(statusConcurrency, items.length) },
      async () => {
        while (next < items.length) await action(items[next++]);
      },
    ),
  );
}

/** File handles wait in memory; only two individual multipart bodies are materialized. */
export function PdfImports({ onAccepted }: { onAccepted: () => void }) {
  const [rows, setRows] = useState<Row[]>(restore);
  const current = useRef(rows);
  current.current = rows;
  const [selection, setSelection] = useState<File[]>([]);
  const selected = useRef<File[]>([]);
  const [notice, setNotice] = useState("");
  const [dragging, setDragging] = useState(false);
  const form = useRef<HTMLFormElement>(null);
  const alive = useRef(true);
  const controller = useRef(new AbortController());
  const activeUploads = useRef(new Set<string>());
  const reading = useRef(new Set<string>());
  const mutatingPapers = useRef(new Set<string>());
  const generations = useRef<Record<string, number>>({});
  const callback = useRef(onAccepted);
  callback.current = onAccepted;
  function update(change: (rows: Row[]) => Row[]) {
    if (!alive.current) return;
    current.current = change(current.current);
    persist(current.current);
    setRows(current.current);
  }
  function change(id: string, values: Partial<Row>) {
    update((items) =>
      items.map((row) => (row.id === id ? { ...row, ...values } : row)),
    );
  }
  function choose(files: File[]) {
    if (files.length > selectionLimit) {
      setNotice(`每次最多选择 ${selectionLimit} 个文件，请分批选择。`);
      return;
    }
    selected.current = files;
    setSelection(files);
    setNotice("");
  }
  function enqueue() {
    if (!form.current || !selected.current.length) return;
    const data = new FormData(form.current);
    const files = selected.current;
    if (
      current.current.filter((row) =>
        ["waiting", "uploading"].includes(row.stage),
      ).length +
        files.length >
      selectionLimit
    ) {
      setNotice("待上传文件最多 100 个，请等待当前上传完成后再添加。");
      return;
    }
    const shared: Metadata = Object.fromEntries(
      ["title", "authors", "year", "venue"].map((key) => [
        key,
        String(data.get(key) ?? "").trim(),
      ]),
    ) as Metadata;
    selected.current = [];
    setSelection([]);
    const input = form.current.elements.namedItem("file") as HTMLInputElement;
    input.value = "";
    update((items) => [
      ...items,
      ...files.map((file): Row => ({
        id: crypto.randomUUID(),
        name: file.name,
        file,
        stage: "waiting",
        metadata: { ...shared, title: files.length === 1 ? shared.title : "" },
      })),
    ]);
    setNotice(
      "文件已加入本页上传列表。上传被接受后，解析和索引由后台继续执行。",
    );
  }
  async function upload(row: Row) {
    if (!row.file || activeUploads.current.has(row.id)) return;
    activeUploads.current.add(row.id);
    const generation = (generations.current[row.id] ?? 0) + 1;
    generations.current[row.id] = generation;
    change(row.id, { stage: "uploading", error: "", uncertain: false });
    let submitted = false;
    try {
      if (row.file.size > maxFileBytes)
        throw new Error(errorMessage("pdf_too_large"));
      if ((await row.file.slice(0, 5).text()) !== "%PDF-")
        throw new Error(errorMessage("invalid_pdf"));
      if (!alive.current) return;
      const data = new FormData();
      data.set("file", row.file);
      for (const [key, value] of Object.entries(row.metadata ?? {}))
        if (value) data.set(key, value);
      submitted = true;
      const receipt = await api(
        "/api/papers/upload",
        UploadReceipt,
        data,
        "POST",
        AbortSignal.any([
          controller.current.signal,
          AbortSignal.timeout(60000),
        ]),
      );
      if (!alive.current || generations.current[row.id] !== generation) return;
      change(row.id, {
        paperId: receipt.paper_id,
        runId: receipt.id,
        run: receipt,
        reused: receipt.reused_existing,
        stage:
          receipt.status === "completed"
            ? "indexed"
            : ["failed", "cancelled"].includes(receipt.status)
              ? "index_failed"
              : "processing",
        file: undefined,
        metadata: undefined,
        error: receipt.error_code ? errorMessage(receipt.error_code) : "",
      });
      callback.current();
      void readStatus(row.id);
    } catch (failure) {
      if (alive.current && generations.current[row.id] === generation)
        change(row.id, {
          stage: "upload_failed",
          error: String(failure),
          uncertain: submitted,
        });
    } finally {
      activeUploads.current.delete(row.id);
      // A state update is necessary to release the next slot even on failure.
      if (alive.current) update((items) => [...items]);
    }
  }
  async function readStatus(id: string) {
    const row = current.current.find((item) => item.id === id);
    if (
      !row?.paperId ||
      !row.runId ||
      reading.current.has(row.paperId) ||
      mutatingPapers.current.has(row.paperId)
    )
      return;
    const paperId = row.paperId,
      generation = generations.current[id] ?? 0;
    reading.current.add(paperId);
    const signal = AbortSignal.any([
      controller.current.signal,
      AbortSignal.timeout(10000),
    ]);
    try {
      const paper = await api(
        `/api/papers/${paperId}`,
        Paper,
        undefined,
        "GET",
        signal,
      );
      const runId = paper.latest_ingestion_run_id ?? row.runId;
      const run = await api(
        `/api/runs/${runId}`,
        Run,
        undefined,
        "GET",
        signal,
      );
      if (
        !alive.current ||
        (generations.current[id] ?? 0) !== generation ||
        mutatingPapers.current.has(paperId)
      )
        return;
      const stage: Stage =
        paper.status === "indexed"
          ? "indexed"
          : paper.status === "failed" ||
              ["failed", "cancelled"].includes(run.status)
            ? "index_failed"
            : "processing";
      update((items) =>
        items.map((item) =>
          item.paperId === paperId
            ? {
                ...item,
                paper,
                run,
                runId,
                stage,
                name: item.name === paperId ? paper.title : item.name,
                error:
                  (run.error_code ?? paper.error_code)
                    ? errorMessage(run.error_code ?? paper.error_code)
                    : "",
                uncertain: false,
                retrying: false,
              }
            : item,
        ),
      );
      if (stage === "indexed" && row.stage !== "indexed") callback.current();
    } catch (failure) {
      if (!alive.current || (generations.current[id] ?? 0) !== generation)
        return;
      const removed = String(failure).includes("source_deleted");
      change(id, {
        ...(removed ? { stage: "unavailable" as const } : {}),
        error: String(failure),
      });
    } finally {
      reading.current.delete(paperId);
    }
  }
  const refresh = async (all = false) => {
    const unique = new Map<string, Row>();
    for (const row of current.current)
      if (row.paperId && (all || row.stage === "processing"))
        unique.set(row.paperId, row);
    await bounded([...unique.values()], (row) => readStatus(row.id));
  };
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;
  useEffect(() => {
    alive.current = true;
    void refreshRef.current(true);
    const tick = () => {
      if (document.visibilityState !== "hidden") void refreshRef.current();
    };
    const timer = setInterval(tick, 5000);
    window.addEventListener("focus", tick);
    window.addEventListener("online", tick);
    document.addEventListener("visibilitychange", tick);
    const warn = (event: BeforeUnloadEvent) => {
      if (
        current.current.some((row) =>
          ["waiting", "uploading"].includes(row.stage),
        )
      ) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      alive.current = false;
      controller.current.abort();
      clearInterval(timer);
      window.removeEventListener("focus", tick);
      window.removeEventListener("online", tick);
      document.removeEventListener("visibilitychange", tick);
      window.removeEventListener("beforeunload", warn);
    };
  }, []);
  useEffect(() => {
    const slots = uploadConcurrency - activeUploads.current.size;
    if (slots > 0)
      for (const row of current.current
        .filter((row) => row.stage === "waiting")
        .slice(0, slots))
        void upload(row);
  }, [rows]);
  async function retryIndex(row: Row) {
    if (!row.paperId || mutatingPapers.current.has(row.paperId)) return;
    const paperId = row.paperId;
    mutatingPapers.current.add(paperId);
    for (const item of current.current.filter(
      (item) => item.paperId === paperId,
    ))
      generations.current[item.id] = (generations.current[item.id] ?? 0) + 1;
    update((items) =>
      items.map((item) =>
        item.paperId === paperId
          ? { ...item, retrying: true, error: "" }
          : item,
      ),
    );
    try {
      const run = await api(
        `/api/papers/${paperId}/retry`,
        Run,
        {},
        "POST",
        AbortSignal.any([
          controller.current.signal,
          AbortSignal.timeout(30000),
        ]),
      );
      update((items) =>
        items.map((item) =>
          item.paperId === paperId
            ? {
                ...item,
                run,
                runId: run.id,
                stage: "processing",
                retrying: false,
              }
            : item,
        ),
      );
      callback.current();
    } catch (failure) {
      update((items) =>
        items.map((item) =>
          item.paperId === paperId
            ? {
                ...item,
                error: `重试结果待核对，请读取最新任务。${String(failure)}`,
                retrying: false,
                uncertain: true,
              }
            : item,
        ),
      );
    } finally {
      mutatingPapers.current.delete(paperId);
      void readStatus(row.id);
    }
  }
  const failures = rows.filter(
    (row) => row.stage === "upload_failed" || row.stage === "index_failed",
  ).length;
  return (
    <div>
      <form
        ref={form}
        aria-label="PDF 导入"
        onSubmit={(event) => {
          event.preventDefault();
          enqueue();
        }}
      >
        <div
          className={`pdf-drop-zone ${dragging ? "dragging" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            choose(Array.from(event.dataTransfer.files));
          }}
          aria-label="拖拽 PDF 文件区域"
        >
          <label>
            PDF
            <input
              name="file"
              type="file"
              accept="application/pdf,.pdf"
              multiple
              required={!selection.length}
              onChange={(event) => choose(Array.from(event.target.files ?? []))}
            />
          </label>
          <p>
            可多选或拖拽 PDF。每次最多 100 个、每个最多 30 MiB，同时上传最多 2
            篇。
          </p>
          {selection.length > 0 && (
            <p role="status">已选择 {selection.length} 个文件；尚未上传。</p>
          )}
        </div>
        <div className="grid">
          <label>
            标题
            <input name="title" maxLength={1000} />
          </label>
          <label>
            作者（分号分隔）
            <input name="authors" maxLength={4000} />
          </label>
          <label>
            年份
            <input name="year" type="number" min="1000" max="2100" />
          </label>
          <label>
            会议 / 期刊
            <input name="venue" maxLength={256} />
          </label>
        </div>
        <p>
          单篇可填写标题；多篇使用各自文件名作为标题，作者/年份/会议字段应用于本次选择的全部文件，导入后可逐篇修改。
        </p>
        <button disabled={!selection.length}>上传并建立索引</button>
      </form>
      {notice && <p role="status">{notice}</p>}
      {rows.length > 0 && (
        <section aria-label="PDF 导入进度">
          <h3>逐篇上传与索引</h3>
          <p role="status">
            已索引 {rows.filter((row) => row.stage === "indexed").length} 项 ·
            失败 {failures} 项 · 等待上传{" "}
            {rows.filter((row) => row.stage === "waiting").length} 项 · 上传中{" "}
            {rows.filter((row) => row.stage === "uploading").length} 项 ·
            解析/索引中{" "}
            {rows.filter((row) => row.stage === "processing").length} 项 ·
            复用已有文献 {rows.filter((row) => row.reused).length} 项
          </p>
          <p>
            上传被接受不等于索引完成。刷新或离开本页会丢弃尚未上传的文件选择；已接受的后台任务继续运行。本地仅保存最近
            50 个论文/任务 ID 用于查询，不保存 PDF、上传内容或持久化队列。
          </p>
          <button onClick={() => void refresh(true)}>刷新导入状态</button>
          <table aria-label="逐篇 PDF 导入">
            <thead>
              <tr>
                <th>文件</th>
                <th>上传阶段</th>
                <th>解析与索引</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} data-import-id={row.id}>
                  <td>
                    {row.name}
                    {row.reused && (
                      <small>
                        服务端按 PDF 内容识别重复，复用已有文献与任务
                      </small>
                    )}
                    {row.paperId && <small>文献：{row.paperId}</small>}
                  </td>
                  <td>
                    {row.paperId
                      ? "已接受上传"
                      : row.stage === "waiting"
                        ? "等待上传"
                        : row.stage === "uploading"
                          ? "上传中，尚未解析"
                          : row.uncertain
                            ? "上传结果待核对"
                            : "上传失败"}
                  </td>
                  <td>
                    {row.stage === "indexed"
                      ? "已完成索引"
                      : row.stage === "index_failed"
                        ? "解析/索引失败"
                        : row.stage === "unavailable"
                          ? "来源已删除"
                          : row.paper?.status === "parsing"
                            ? "正在解析 PDF"
                            : row.paper?.status === "indexing"
                              ? "正在建立索引"
                              : row.paperId
                                ? "后台排队或读取状态中"
                                : "尚未开始"}
                    {row.error && <p role="alert">{row.error}</p>}
                  </td>
                  <td>
                    {row.stage === "upload_failed" && row.file && (
                      <button
                        onClick={() => {
                          generations.current[row.id] =
                            (generations.current[row.id] ?? 0) + 1;
                          change(row.id, { stage: "waiting", error: "" });
                        }}
                      >
                        核对并重试此文件上传
                      </button>
                    )}
                    {row.paperId && row.stage !== "unavailable" && (
                      <button onClick={() => void readStatus(row.id)}>
                        读取此篇最新状态
                      </button>
                    )}
                    {row.paperId &&
                      (row.stage === "index_failed" ||
                        row.run?.error_code === "queue_unavailable") && (
                        <button
                          disabled={row.retrying}
                          onClick={() => void retryIndex(row)}
                        >
                          {row.retrying
                            ? "正在提交重试…"
                            : "重试此篇解析与索引"}
                        </button>
                      )}
                    {row.paperId && (
                      <details
                        onToggle={(event) => {
                          if (event.currentTarget.open) void readStatus(row.id);
                        }}
                      >
                        <summary>查看索引结果</summary>
                        <p>
                          状态：
                          {row.paper?.status ?? row.run?.status ?? "正在查询"}
                          ；文本块：{row.paper?.chunk_count ?? "尚未读取"}
                        </p>
                        <small>
                          任务：{row.runId} · {row.run?.error_code ?? ""}
                        </small>
                        {row.stage !== "unavailable" && (
                          <a
                            href={`/api/papers/${row.paperId}/pdf`}
                            target="_blank"
                            rel="noreferrer"
                            onClick={(event) => {
                              if (isDesktop()) {
                                event.preventDefault();
                                void openPaperPdf(row.paperId!).catch(
                                  (failure) =>
                                    change(row.id, { error: String(failure) }),
                                );
                              }
                            }}
                          >
                            打开此篇原始 PDF
                          </a>
                        )}
                      </details>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
