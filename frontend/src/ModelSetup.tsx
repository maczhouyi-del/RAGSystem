import { useEffect, useState } from "react";
import { z } from "zod";
import { Mapping, Model, api } from "./api";

export const MODEL_CONFIG_UPDATED = "ragagent-model-config-updated";
const roles = ["supervisor", "retriever", "analyst", "reviewer"] as const;
const defaults: Record<
  string,
  { label: string; model: string; base: string | null; key: string | null }
> = {
  openai: {
    label: "OpenAI",
    model: "gpt-4.1-mini-2025-04-14",
    base: null,
    key: "OPENAI_API_KEY",
  },
  deepseek: {
    label: "DeepSeek",
    model: "deepseek-chat",
    base: null,
    key: "DEEPSEEK_API_KEY",
  },
  anthropic: {
    label: "Anthropic",
    model: "claude-sonnet-4-20250514",
    base: null,
    key: "ANTHROPIC_API_KEY",
  },
  ollama_chat: {
    label: "本地 Ollama",
    model: "qwen3:8b",
    base: "http://host.docker.internal:11434",
    key: null,
  },
  openai_compatible: {
    label: "其他 OpenAI 兼容服务",
    model: "",
    base: "",
    key: "OPENAI_API_KEY",
  },
};
export type Check = "connection" | "inference";
export const TestResult = z.object({
  ok: z.boolean(),
  model: z.string(),
  model_advertised: z.boolean().optional(),
});

export function ModelTestConfirmation({
  agent,
  check,
  onConfirm,
  onCancel,
}: {
  agent: string;
  check: Check;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <dialog
      open
      className="confirm-dialog"
      aria-label="模型测试确认"
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
    >
      <h3>确认模型{check === "connection" ? "连接" : "推理"}测试</h3>
      <p>测试对象：当前已保存的 {agent} 模型。</p>
      <p>
        {check === "connection"
          ? "将查询服务商的模型目录，不生成答案。目录可连接不代表模型可推理；外部请求可能产生费用，以服务商政策为准。"
          : "将向服务商发送一条固定测试指令，不发送论文或会话。会实际生成少量 Token，可能产生费用，失败或重试也可能收费。"}
      </p>
      <p>只有点击确认才发送请求。测试不能证明真实科研质量。</p>
      <button onClick={onCancel}>取消测试</button>
      <button onClick={onConfirm}>
        确认并开始{check === "connection" ? "连接" : "推理"}测试
      </button>
    </dialog>
  );
}

export function ModelSetup({
  mapping,
  disabled,
  onSaved,
  onBusyChange,
}: {
  mapping: Mapping;
  disabled: boolean;
  onSaved: () => Promise<void>;
  onBusyChange: (busy: boolean) => void;
}) {
  const [provider, setProvider] =
    useState<z.infer<typeof Model>["provider"]>("openai");
  const [model, setModel] = useState("");
  const [base, setBase] = useState("");
  const [busy, setBusy] = useState(false);
  const [saveConfirm, setSaveConfirm] = useState(false);
  const [testConfirm, setTestConfirm] = useState<Check | null>(null);
  const [connection, setConnection] = useState<
    "not_tested" | "success" | "failed"
  >("not_tested");
  const [inference, setInference] = useState<
    "not_tested" | "passed" | "failed"
  >("not_tested");
  const [message, setMessage] = useState("");
  const [advertised, setAdvertised] = useState<boolean | null>(null);
  const saved = mapping.agents.supervisor;
  useEffect(() => {
    const current = mapping.agents.supervisor;
    if (current) {
      setProvider(current.provider);
      setModel(current.model);
      setBase(current.api_base ?? "");
    }
    setConnection("not_tested");
    setInference("not_tested");
    setAdvertised(null);
    setSaveConfirm(false);
    setTestConfirm(null);
  }, [mapping]);
  const preset = defaults[provider];
  const same =
    !!saved &&
    roles.every((role) => {
      const m = mapping.agents[role];
      return (
        m &&
        m.provider === provider &&
        m.model === model.trim() &&
        (m.api_base ?? "") === base.trim() &&
        (m.api_key_env ?? null) === preset.key
      );
    });
  const draft =
    model.trim() !== (saved?.model ?? "") ||
    provider !== saved?.provider ||
    base.trim() !== (saved?.api_base ?? "");
  async function save() {
    if (disabled || busy || !model.trim()) return;
    setSaveConfirm(false);
    setBusy(true);
    onBusyChange(true);
    setMessage("");
    try {
      const roleModel = {
        provider,
        model: model.trim(),
        api_base: base.trim() || null,
        api_key_env: preset.key,
      };
      await api(
        "/api/providers",
        z.object({ status: z.string() }),
        { agents: Object.fromEntries(roles.map((role) => [role, roleModel])) },
        "PUT",
      );
      setConnection("not_tested");
      setInference("not_tested");
      setMessage("四个角色配置已保存；密钥是否存在与模型推理需要分别检查。");
      await onSaved();
      window.dispatchEvent(new Event(MODEL_CONFIG_UPDATED));
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "保存未完成，请重试。不会清除论文或会话。",
      );
    } finally {
      setBusy(false);
      onBusyChange(false);
    }
  }
  async function test(check: Check) {
    if (disabled || busy || draft || !saved) return;
    setTestConfirm(null);
    setBusy(true);
    onBusyChange(true);
    setMessage("正在执行你确认的测试…");
    try {
      const result = await api("/api/providers/test", TestResult, {
        agent: "supervisor",
        check,
      });
      setConnection("success");
      if (check === "connection") {
        setAdvertised(result.model_advertised ?? null);
        setMessage(
          "模型目录连接成功；尚未验证模型推理。没有自动发起推理测试。",
        );
      } else {
        setInference(result.ok ? "passed" : "failed");
        setMessage(
          result.ok
            ? "本次固定测试推理通过；论文解析、Embedding、其他角色及科研质量需独立验证。"
            : "服务返回了响应，但本次推理测试未通过。检查模型是否支持 JSON 输出或在高级设置选择其他模型后重试。",
        );
      }
    } catch (error) {
      if (check === "connection") setConnection("failed");
      else setInference("failed");
      setMessage(
        error instanceof Error
          ? error.message
          : "测试未完成，请检查配置后主动重试。",
      );
    } finally {
      setBusy(false);
      onBusyChange(false);
    }
  }
  return (
    <section className="model-setup panel" aria-label="首次模型配置">
      <h3>选择一个聊天模型开始使用</h3>
      <p>
        同一模型可以先用于四个角色：Supervisor、Retriever、Analyst、Reviewer。以后可在下方高级设置分别调整，不需要编辑
        YAML。
      </p>
      <p>
        已载入当前配置，不会自动覆盖。模型名称是参考值，请使用服务商账户实际支持的模型；保存本身不会调用模型。
      </p>
      <fieldset disabled={disabled || busy}>
        <legend>聊天模型快捷配置</legend>
        <label>
          服务商
          <select
            aria-label="服务商"
            value={provider}
            onChange={(event) => {
              const value = Model.shape.provider.parse(event.target.value);
              const next = defaults[value];
              setProvider(value);
              setModel(next.model);
              setBase(next.base ?? "");
              setMessage("");
            }}
          >
            {Object.entries(defaults).map(([value, p]) => (
              <option key={value} value={value}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          聊天模型名称
          <input
            value={model}
            autoComplete="off"
            onChange={(event) => setModel(event.target.value)}
          />
        </label>
        <label>
          服务地址（官方服务可留空）
          <input
            value={base}
            autoComplete="off"
            onChange={(event) => setBase(event.target.value)}
            placeholder={
              provider === "openai_compatible"
                ? "https://你的服务地址/v1"
                : "使用服务商默认地址"
            }
          />
        </label>
        <p>
          {preset.key
            ? `API Key 请在图形部署助手中选择 ${provider === "openai_compatible" ? "OpenAI（兼容服务共用 OPENAI_API_KEY）" : preset.label}，使用隐藏输入保存，随后启动系统使密钥生效。此网页/桌面表单不接收密钥。`
            : "Ollama 默认无需 API Key。先在个人电脑启动 Ollama 并下载所选模型；Docker 后端需要能访问该服务地址。Linux 如无法解析 host.docker.internal，请在高级设置填可达地址。"}
        </p>
        <button
          disabled={
            !model.trim() ||
            same ||
            (provider === "openai_compatible" && !base.trim())
          }
          onClick={() => setSaveConfirm(true)}
        >
          为四个角色保存此配置
        </button>
      </fieldset>
      <dl className="model-states">
        <div>
          <dt>配置已保存</dt>
          <dd>
            {draft ? "有未保存修改，先保存后测试" : "已读取服务器保存的配置"}
          </dd>
        </div>
        <div>
          <dt>密钥存在</dt>
          <dd>
            {saved?.key_configured
              ? saved.provider === "ollama_chat" && !saved.api_key_env
                ? "本地模型无需密钥"
                : "存在；有效性尚需连接测试"
              : "未配置或尚无法读取；请用部署助手保存并启动，然后刷新"}
          </dd>
        </div>
        <div>
          <dt>连接测试成功</dt>
          <dd>
            {connection === "success"
              ? "本次测试成功"
              : connection === "failed"
                ? "本次检查未通过，按提示恢复后重试"
                : "尚未测试"}
          </dd>
        </div>
        <div>
          <dt>模型可实际推理</dt>
          <dd>
            {inference === "passed"
              ? "本次固定测试通过；不代表科研质量"
              : inference === "failed"
                ? "本次测试未通过"
                : "尚未测试"}
          </dd>
        </div>
      </dl>
      <p>
        测试针对当前已保存的
        Supervisor；若四角色配置不同，请在高级设置分别测试。测试状态仅在本次页面保留，重新打开后不自动产生请求。
      </p>
      {advertised === false && (
        <p role="alert">
          服务可连接，但目录未列出当前模型。核对模型名/权限；某些服务目录不完整，是否能推理仍需你主动测试。
        </p>
      )}
      <div className="inline">
        <button
          disabled={disabled || busy || draft || !saved}
          onClick={() => setTestConfirm("connection")}
        >
          检查模型连接
        </button>
        <button
          disabled={disabled || busy || draft || !saved}
          onClick={() => setTestConfirm("inference")}
        >
          测试模型推理（可能收费）
        </button>
        <button
          disabled={disabled || busy}
          onClick={() => {
            setBusy(true);
            onBusyChange(true);
            void onSaved()
              .then(() =>
                setMessage("已刷新保存配置与密钥存在状态；没有执行模型测试。"),
              )
              .catch(() =>
                setMessage("状态刷新失败，请检查本机授权或诊断后重试。"),
              )
              .finally(() => {
                setBusy(false);
                onBusyChange(false);
              });
          }}
        >
          刷新配置与密钥状态
        </button>
      </div>
      {message && <p role="status">{message}</p>}
      {saveConfirm && (
        <dialog
          open
          className="confirm-dialog"
          aria-label="默认角色映射确认"
          onCancel={(event) => {
            event.preventDefault();
            setSaveConfirm(false);
          }}
        >
          <h3>确认应用到四个角色</h3>
          <p>
            {preset.label} · {model}
            。将替换四个角色现有的服务商、模型、地址和密钥变量映射。私有密钥、论文、索引与会话保持不变。
          </p>
          <p>已有高级角色设置如需保留，请取消并使用下方高级设置。</p>
          <button onClick={() => setSaveConfirm(false)}>取消保存</button>
          <button onClick={() => void save()}>确认保存四角色配置</button>
        </dialog>
      )}
      {testConfirm && (
        <ModelTestConfirmation
          agent="Supervisor"
          check={testConfirm}
          onCancel={() => setTestConfirm(null)}
          onConfirm={() => void test(testConfirm)}
        />
      )}
    </section>
  );
}
