import { useCallback, useEffect, useRef, useState } from "react";
import { z } from "zod";
import { api } from "./api";
import { DiagnosticSnapshot, Diagnostics } from "./Diagnostics";
import { request } from "./transport";

const preferenceKey = "ragagent.first-use.dismissed.v1";
const AuthStatus = z.object({
  initialized: z.boolean(),
  authenticated: z.boolean(),
});
const roles = ["supervisor", "retriever", "analyst", "reviewer"] as const;
const ChatConfiguration = z.record(
  z.string(),
  z.object({ credential_configured: z.boolean() }),
);
type Snapshot = z.infer<typeof DiagnosticSnapshot>;
type Destination = "Settings" | "Knowledge Base" | "RAG";

function wasDismissed(): boolean {
  try {
    return localStorage.getItem(preferenceKey) === "true";
  } catch {
    return false;
  }
}

export function FirstUseGuide({
  authRevision,
  onAuthorize,
  onNavigate,
}: {
  authRevision: number;
  onAuthorize: () => void;
  onNavigate: (page: Destination) => void;
}) {
  const [mode, setMode] = useState<"auto" | "open" | "closed">(() =>
    wasDismissed() ? "closed" : "auto",
  );
  const [firstUse, setFirstUse] = useState(false);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [auth, setAuth] = useState<z.infer<typeof AuthStatus> | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const sequence = useRef(0);
  const active = useRef(false);
  const visible = mode === "open" || (mode === "auto" && firstUse);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    const current = ++sequence.current;
    active.current = true;
    const probeSignal = signal
      ? AbortSignal.any([signal, AbortSignal.timeout(10000)])
      : AbortSignal.timeout(10000);
    const valid = () => !signal?.aborted && current === sequence.current;
    setBusy(true);
    let live = false;
    let authorization: z.infer<typeof AuthStatus> | null = null;
    let details: Snapshot | null = null;
    let message = "";
    try {
      const response = await request("/api/health", { signal: probeSignal });
      const health = z
        .object({ status: z.literal("ok") })
        .parse(await response.json());
      live = response.ok && health.status === "ok";
      if (!live) throw new Error("backend_unavailable");
      authorization = await api(
        "/api/auth/status",
        AuthStatus,
        undefined,
        "GET",
        probeSignal,
      );
      if (authorization.authenticated) {
        details = await api(
          "/api/diagnostics",
          DiagnosticSnapshot,
          undefined,
          "GET",
          probeSignal,
        );
      }
    } catch {
      message = live
        ? "详细状态暂不可读取：重新检查，或打开本机授权；在 Settings 的诊断中确认数据库、Redis 和 worker。"
        : "后端不可用：先启动 Docker Desktop / Docker Engine，再打开部署助手选择启动；检查 Docker 状态、端口与依赖，详见安装教程。";
    } finally {
      if (current === sequence.current) {
        active.current = false;
        setBusy(false);
      }
      if (valid()) {
        setConnected(live);
        setAuth(authorization);
        setSnapshot(details);
        setNotice(message);
        // Existing indexed libraries enter their original interface, even when
        // model settings need attention. The guide never resets server data.
        setFirstUse(
          (previous) =>
            previous ||
            !live ||
            authorization?.authenticated === false ||
            details?.corpus?.state === "empty",
        );
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, [refresh, authRevision]);
  useEffect(() => {
    if (!visible || connected !== true) return;
    const controller = new AbortController();
    const timer = setInterval(() => {
      if (!active.current) void refresh(controller.signal);
    }, 5000);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [refresh, visible, authRevision, connected]);

  function dismiss() {
    setMode("closed");
    try {
      // UI preference only: no credentials, corpus or conversation identifiers.
      localStorage.setItem(preferenceKey, "true");
    } catch {
      // Storage unavailable: closing still works for this window.
    }
  }
  const config = ChatConfiguration.safeParse(snapshot?.chat_configuration);
  const modelsConfigured =
    config.success &&
    roles.every((role) => config.data[role]?.credential_configured === true);
  const indexed = snapshot?.corpus?.state === "available";
  const infrastructure =
    snapshot?.database === "available" &&
    snapshot?.redis === "available" &&
    (snapshot?.queues?.interactive?.workers ?? 0) > 0 &&
    (snapshot?.queues?.ingestion?.workers ?? 0) > 0;
  const missingDependencies = Object.values(
    snapshot?.runtime_dependencies ?? {},
  ).includes("missing");

  return (
    <div className="first-use-container">
      {!visible ? (
        <button
          onClick={() => {
            setMode("open");
            void refresh();
          }}
        >
          首次使用引导
        </button>
      ) : (
        <section className="first-use-guide" aria-label="首次使用引导">
          <div className="inline">
            <h2>开始使用文献助手</h2>
            <button onClick={dismiss}>关闭引导</button>
            <button disabled={busy} onClick={() => void refresh()}>
              刷新引导状态
            </button>
          </div>
          <p>
            必需：连接、本机授权、模型配置、可用文献。可选：连接测试（可能收费）。可以随时关闭或重新打开，不会清除文献、会话或记忆。
          </p>
          {notice && <p role="status">{notice}</p>}
          <ol>
            <li>
              <strong>检查连接与基础服务</strong>
              <p>
                {connected === null
                  ? "正在检查连接…"
                  : !connected
                    ? "后端尚未连接"
                    : infrastructure
                      ? "数据库、Redis 与问答/索引 worker 可用"
                      : !auth?.authenticated
                        ? "后端在线；基础服务需在授权后检查"
                        : snapshot
                          ? "后端在线；数据库、Redis 或问答/索引 worker 不可用"
                          : "后端在线；详细状态暂不可读取"}
              </p>
              {snapshot && !infrastructure && (
                <p>
                  基础服务未就绪：打开诊断，检查数据库/Redis，并启动
                  worker-interactive 与 worker-ingestion。
                </p>
              )}
            </li>
            <li>
              <strong>完成本机授权</strong>
              <p>
                {auth?.authenticated
                  ? "本机授权已通过"
                  : auth?.initialized === false
                    ? "后端尚未配对：打开本机授权，完成配对并重启后端"
                    : "打开本机授权，检查配对与连接"}
              </p>
              <button onClick={onAuthorize}>前往本机授权</button>
            </li>
            <li>
              <strong>检查模型配置</strong>
              <p>
                {modelsConfigured
                  ? "四个聊天角色已配置；真实推理尚未验证"
                  : "聊天模型未配置或尚无法检查；没有 API Key 也可以先做环境诊断"}
              </p>
              <p>
                可选连接测试在 Settings
                中手动执行，可能产生费用；服务就绪不代表模型推理成功。
              </p>
              <button onClick={() => onNavigate("Settings")}>
                检查模型设置
              </button>
            </li>
            <li>
              <strong>上传第一篇论文</strong>
              <p>
                选择 PDF 后在 Knowledge Base 上传。解析、Embedding
                和模型下载可能需要时间；使用远程 Embedding 时可能收费。
              </p>
              {missingDependencies && (
                <p>
                  后端解析或本地模型依赖缺失：按环境诊断建议重建镜像或安装可选依赖后再索引。
                </p>
              )}
              <button
                disabled={!auth?.authenticated}
                onClick={() => onNavigate("Knowledge Base")}
              >
                上传第一篇论文
              </button>
            </li>
            <li>
              <strong>等待索引完成</strong>
              <p>
                {indexed
                  ? `已有 ${snapshot?.corpus?.usable_papers ?? ""} 篇可用文献`
                  : snapshot?.corpus?.state === "empty"
                    ? "尚无可用文献：上传成功不代表索引完成；等待列表出现 indexed 和来源片段"
                    : "索引状态尚无法检查，请完成授权或刷新诊断"}
              </p>
            </li>
            <li>
              <strong>发起第一次问答</strong>
              <p>
                打开 RAG
                后输入论文相关问题，再点击发送；远程模型调用可能收费。答案仍需核对原文与引用。
              </p>
              <button
                disabled={
                  !indexed ||
                  !modelsConfigured ||
                  !infrastructure ||
                  missingDependencies
                }
                onClick={() => onNavigate("RAG")}
              >
                打开首次问答
              </button>
            </li>
          </ol>
          <Diagnostics />
        </section>
      )}
    </div>
  );
}
