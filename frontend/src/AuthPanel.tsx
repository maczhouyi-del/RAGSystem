import { useEffect, useState } from "react";
import { isDesktop, localCredentialStatus, request } from "./transport";

export function AuthPanel({ onConnected }: { onConnected: () => void }) {
  const [hash, setHash] = useState<string | null>(null);
  const [copyStatus, setCopyStatus] = useState("");
  const [token, setToken] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (isDesktop())
      void localCredentialStatus().then(
        (value) => {
          setHash(value.tokenHash);
          if (!value.available)
            setStatus(
              "系统凭据库不可用，请检查系统钥匙串或 Credential Manager。",
            );
        },
        () => setStatus("无法读取系统凭据状态。"),
      );
  }, []);
  async function connect() {
    setBusy(true);
    setStatus("");
    try {
      if (!isDesktop() && token) {
        const response = await request("/api/auth/session", {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) throw new Error("auth_failed");
      }
      const response = await request("/api/auth/status");
      const value: { authenticated: boolean; initialized: boolean } =
        await response.json();
      if (response.ok && value.authenticated) onConnected();
      else
        setStatus(
          value.initialized
            ? "授权失败，请核对凭据与后端配置。"
            : "后端尚未配置授权，请完成本机配对并重启后端。",
        );
    } catch {
      setStatus("连接或授权失败，请检查本机后端与配对配置。");
    } finally {
      setToken("");
      setBusy(false);
    }
  }
  return (
    <section className="panel" aria-label="本机连接授权">
      <h2>本机连接授权</h2>
      {isDesktop() ? (
        <>
          <p>
            打开图形部署助手的本机授权步骤，粘贴下方配对哈希，再按向导启动。已有配对可直接连接，无需重复初始化。
            凭据由系统凭据库保存。
          </p>
          {hash && (
            <>
              <pre aria-label="配对哈希">{hash}</pre>
              <button
                onClick={() => {
                  void (async () => {
                    try {
                      await navigator.clipboard.writeText(hash);
                      setCopyStatus(
                        "配对哈希已复制。粘贴到图形助手的本机授权步骤。",
                      );
                    } catch {
                      setCopyStatus(
                        "系统不允许复制，请选中上方哈希手动复制；不会改动现有凭据。",
                      );
                    }
                  })();
                }}
              >
                复制配对哈希
              </button>
              {copyStatus && <p role="status">{copyStatus}</p>}
            </>
          )}
        </>
      ) : (
        <>
          <p>
            Web 模式先在部署助手选择 Web 配对，再输入你选定的本机 Web 凭据。
            授权在 HttpOnly 会话中保存，后端重启后需重新授权。
          </p>
          <label>
            Web 本机凭据
            <input
              type="password"
              autoComplete="off"
              value={token}
              onChange={(event) => setToken(event.target.value)}
            />
          </label>
        </>
      )}
      <button disabled={busy} onClick={() => void connect()}>
        连接并检查授权
      </button>
      {status && <p role="alert">{status}</p>}
    </section>
  );
}
