import { useEffect, useState } from "react";
import { z } from "zod";
import { api } from "./api";
import { errorMessage } from "./errors";

const token = z.object({
  known: z.number().int().nonnegative().nullable(),
  complete: z.boolean(),
  reported_calls: z.number().int().nonnegative().nullable(),
});
export const Metrics = z.object({
  run_id: z.string().uuid(),
  kind: z.string(),
  status: z.string(),
  error_code: z.string().nullable(),
  retryable: z.boolean(),
  usage_scope: z.string().nullable(),
  input_tokens: token,
  output_tokens: token,
  known_estimate_usd: z.number().nonnegative().nullable(),
  estimate_complete: z.boolean(),
  exact_provider_bill_usd: z.null(),
  total_seconds: z.number().nonnegative().nullable(),
  execution_seconds: z.number().nonnegative().nullable(),
  queue_seconds: z.number().nonnegative().nullable(),
  duration_live: z.boolean(),
  additional_charges_possible: z.boolean(),
  usages: z.array(
    z.object({
      role: z.string(),
      configured_model: z.string().nullable(),
      returned_models: z.array(z.string()),
      calls: z.number().int().nonnegative().nullable(),
      in_flight_calls: z.number().int().nonnegative().nullable(),
      input_tokens: token,
      output_tokens: token,
      cost_basis: z.enum(["sdk_estimate", "local_service", "unknown"]),
      known_amount_usd: z.number().nonnegative().nullable(),
      amount_complete: z.boolean(),
      unknown_cost_calls: z.number().int().nonnegative().nullable(),
    }),
  ),
  phases: z.array(
    z.object({
      phase: z.string(),
      seconds: z.number().nonnegative().nullable(),
      completed_intervals: z.number().int().nonnegative(),
      measured_intervals: z.number().int().nonnegative(),
      basis: z.literal("node_interval"),
    }),
  ),
});
const labels: Record<string, string> = {
  queued: "排队中",
  running: "执行中",
  completed: "已完成",
  insufficient_evidence: "证据不足",
  failed: "执行失败",
  cancelled: "已取消",
  plan: "规划",
  supervisor: "调度",
  retrieve: "检索",
  retriever: "检索",
  analysis: "分析",
  answer: "回答",
  synthesis: "综合",
  reviewer: "校验",
  verify: "校验",
  expand: "扩展检索",
  finish: "发布",
  stop: "停止",
  refuse: "拒答",
};
const tokens = (value: z.infer<typeof token>) =>
  value.known === null
    ? "Unknown"
    : `${value.known}${value.complete ? "" : "（已知部分；总量 Unknown）"}`;
const duration = (value: number | null) =>
  value === null ? "Unknown" : `${value.toFixed(2)} 秒`;
const money = (value: number | null, complete: boolean) =>
  value === null
    ? "Unknown"
    : `USD ${value.toPrecision(6)}${complete ? "" : "（已知部分；总量 Unknown）"}`;

/** Reads persisted local accounting only. Historical rows load on demand. */
export function RunMetrics({
  runId,
  status,
  revision,
}: {
  runId: string;
  status: string;
  revision?: string;
}) {
  const [open, setOpen] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [snapshot, setSnapshot] = useState<z.infer<typeof Metrics> | null>(
    null,
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let reads = 0;
    setPaused(false);
    const read = async () => {
      setBusy(true);
      try {
        const value = await api(
          `/api/runs/${runId}/metrics`,
          Metrics,
          undefined,
          "GET",
          AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]),
        );
        if (controller.signal.aborted) return;
        if (value.run_id !== runId)
          throw new Error("任务统计与当前任务不一致，请重新读取。");
        setSnapshot(value);
        setError("");
        reads++;
        if (["queued", "running"].includes(value.status)) {
          if (reads < 60) timer = setTimeout(() => void read(), 5000);
          else setPaused(true);
        }
      } catch (e) {
        if (!controller.signal.aborted) {
          setError(e instanceof Error ? e.message : "任务统计暂不可用。");
          setPaused(true);
        }
      } finally {
        if (!controller.signal.aborted) setBusy(false);
      }
    };
    void read();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [open, runId, status, revision, refresh]);
  const value = snapshot?.run_id === runId ? snapshot : null;
  return (
    <details
      className="run-metrics"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>模型、用量与耗时</summary>
      {open && (
        <section aria-label="任务统计">
          <button disabled={busy} onClick={() => setRefresh((v) => v + 1)}>
            刷新任务统计
          </button>
          {busy && <p role="status">正在读取本地记录…</p>}
          {error && (
            <p role="alert">
              {error}
              {value && " 显示的是上次读取的记录。"}
            </p>
          )}
          {paused && <p>自动刷新已暂停；可手动刷新本地记录。</p>}
          {value && (
            <>
              <p>
                任务：{value.run_id} · {value.kind} ·{" "}
                {labels[value.status] ?? value.status}
              </p>
              {value.error_code && (
                <p role="status">失败原因：{errorMessage(value.error_code)}</p>
              )}
              <p>
                {value.retryable
                  ? "可使用本轮重试入口重新执行；仍需满足会话与来源条件。"
                  : "当前状态不提供本轮重试。"}
              </p>
              <dl>
                <dt>输入 Token</dt>
                <dd>{tokens(value.input_tokens)}</dd>
                <dt>输出 Token</dt>
                <dd>{tokens(value.output_tokens)}</dd>
                <dt>SDK 费用估算</dt>
                <dd>
                  {money(value.known_estimate_usd, value.estimate_complete)}
                </dd>
                <dt>精确服务商账单</dt>
                <dd>Unknown（尚未导入服务商账单）</dd>
                <dt>总耗时（含排队）</dt>
                <dd>
                  {duration(value.total_seconds)}
                  {value.duration_live && "（截至本次读取）"}
                </dd>
                <dt>执行耗时</dt>
                <dd>{duration(value.execution_seconds)}</dd>
                <dt>排队耗时</dt>
                <dd>{duration(value.queue_seconds)}</dd>
              </dl>
              <p>
                统计范围：
                {value.usage_scope === "current_attempt"
                  ? "当前执行尝试；重试的费用另计"
                  : "Unknown（旧记录未声明范围）"}
                。
              </p>
              {value.usages.length ? (
                <table aria-label="模型用量">
                  <thead>
                    <tr>
                      <th>角色 / 配置模型</th>
                      <th>返回模型</th>
                      <th>调用 / 未完成</th>
                      <th>输入 / 输出 Token</th>
                      <th>已知金额</th>
                    </tr>
                  </thead>
                  <tbody>
                    {value.usages.map((row) => (
                      <tr key={row.role}>
                        <td>
                          {row.role} · {row.configured_model ?? "Unknown"}
                        </td>
                        <td>{row.returned_models.join("、") || "Unknown"}</td>
                        <td>
                          {row.calls ?? "Unknown"} /{" "}
                          {row.in_flight_calls ?? "Unknown"}
                        </td>
                        <td>
                          {tokens(row.input_tokens)} /{" "}
                          {tokens(row.output_tokens)}
                        </td>
                        <td>
                          {row.cost_basis === "sdk_estimate"
                            ? "SDK 估算："
                            : row.cost_basis === "local_service"
                              ? "本地服务调用："
                              : "金额来源 Unknown："}
                          {money(row.known_amount_usd, row.amount_complete)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p>模型与用量：Unknown（尚无可用记录）。</p>
              )}
              {value.phases.length ? (
                <ul aria-label="阶段耗时">
                  {value.phases.map((phase) => (
                    <li key={phase.phase}>
                      {labels[phase.phase] ?? phase.phase}：
                      {duration(phase.seconds)} · {phase.measured_intervals}/
                      {phase.completed_intervals} 个已完成区间有计时
                    </li>
                  ))}
                </ul>
              ) : (
                <p>阶段耗时：Unknown（尚无已完成区间计时）。</p>
              )}
              <p>
                阶段区间包含调度等开销；执行中的未完成阶段尚未计入。旧记录不反推模型推理耗时。
              </p>
              {value.additional_charges_possible && (
                <p>
                  远程请求即使失败或取消，也可能已被服务商计费；取消后的返回费用记录可能稍后补齐，重试可能产生额外费用。
                </p>
              )}
              <p>
                刷新仅读取本地持久化记录，不调用模型。SDK
                估算以美元计，与服务商最终账单可能不同；本地服务调用金额不包含硬件和电力成本。
              </p>
            </>
          )}
        </section>
      )}
    </details>
  );
}
