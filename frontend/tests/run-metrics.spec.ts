import { expect, test, type Page } from "@playwright/test";
import { completed, setupChat } from "./chat-fixtures";

// MOCK local records only. These are neither provider bills nor real model calls.
test("MOCK legacy Run detail reload keeps exactly one export and one metrics panel", async ({
  page,
}) => {
  const chat = await setupChat(page);
  const conversation = chat.create("DEMO legacy reload", "rag");
  const message = chat.makeMessage(
    conversation,
    "assistant",
    "DEMO saved answer",
    {
      ...completed,
      result: { ...completed.result, limitations: ["DEMO Run details loaded"] },
    },
  );
  message.metadata = {};
  await page.goto(`/#/rag/${conversation.id}`);
  await expect.poll(() => chat.fullRunRequests.length).toBe(1);
  await expect(
    page.getByText("DEMO Run details loaded", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "导出当前结果", exact: true }),
  ).toHaveCount(1);
  await expect(page.getByText("模型、用量与耗时", { exact: true })).toHaveCount(
    1,
  );
});

const unknownToken = { known: null, complete: false, reported_calls: null };
function snapshot(status = "completed") {
  return {
    run_id: completed.id,
    kind: "research",
    status,
    error_code: null,
    retryable: ["failed", "cancelled", "insufficient_evidence"].includes(
      status,
    ),
    usage_scope: "current_attempt",
    input_tokens: unknownToken,
    output_tokens: unknownToken,
    known_estimate_usd: null,
    estimate_complete: false,
    exact_provider_bill_usd: null,
    total_seconds: 12,
    execution_seconds: 9,
    queue_seconds: 3,
    duration_live: status === "running",
    additional_charges_possible: true,
    usages: [] as Record<string, unknown>[],
    phases: [] as Record<string, unknown>[],
  };
}
async function show(page: Page, status: string) {
  const chat = await setupChat(page, { holdStream: status === "running" });
  const conversation = chat.create("DEMO accounting", "research");
  chat.makeMessage(
    conversation,
    "assistant",
    status === "completed" ? "DEMO verified report" : "",
    {
      ...completed,
      kind: "research",
      status,
      result: null,
      error_code:
        status === "failed" ? "provider_request_or_schema_failed" : null,
    },
  );
  await page.goto(`/#/research/${conversation.id}`);
  return chat;
}

for (const [status, label] of [
  ["completed", "已完成"],
  ["failed", "执行失败"],
  ["cancelled", "已取消"],
]) {
  test(`MOCK ${status} metrics stay local and show Unknown instead of fabricated zero`, async ({
    page,
  }) => {
    const chat = await show(page, status);
    let reads = 0;
    const methods: string[] = [];
    await page.route(`**/api/runs/${completed.id}/metrics`, (route) => {
      reads++;
      methods.push(route.request().method());
      return route.fulfill({
        json: {
          ...snapshot(status),
          error_code: chat.runs.get(completed.id)?.error_code,
        },
      });
    });
    expect(reads).toBe(0);
    await page.getByText("模型、用量与耗时", { exact: true }).click();
    const panel = page.getByRole("region", { name: "任务统计" });
    await expect(panel).toContainText(label);
    await expect(panel).toContainText("SDK 费用估算Unknown");
    await expect(panel).toContainText("输入 TokenUnknown");
    await expect(panel).toContainText("精确服务商账单Unknown");
    await expect(panel).toContainText("取消后的返回费用记录可能稍后补齐");
    await expect(panel).toContainText("12.00 秒");
    if (status !== "completed")
      await expect(
        page.getByRole("button", { name: "重试本轮", exact: true }),
      ).toBeVisible();
    await panel.getByRole("button", { name: "刷新任务统计" }).click();
    await expect.poll(() => reads).toBe(2);
    expect(methods).toEqual(["GET", "GET"]);
    expect(chat.retries).toBe(0);
  });
}

test("MOCK partial estimate, actual zero output, model identity and repeated stage timings are readable", async ({
  page,
}) => {
  await show(page, "completed");
  const data = {
    ...snapshot(),
    input_tokens: { known: 10, complete: false, reported_calls: null },
    output_tokens: { known: 0, complete: false, reported_calls: null },
    known_estimate_usd: 0.012,
    usages: [
      {
        role: "analyst",
        configured_model: "openai/DEMO-configured",
        returned_models: ["DEMO-returned"],
        calls: 2,
        in_flight_calls: 1,
        input_tokens: { known: 10, complete: false, reported_calls: 1 },
        output_tokens: { known: 0, complete: false, reported_calls: 1 },
        cost_basis: "sdk_estimate",
        known_amount_usd: 0.012,
        amount_complete: false,
        unknown_cost_calls: 1,
      },
    ],
    phases: [
      {
        phase: "retriever",
        seconds: 3,
        completed_intervals: 2,
        measured_intervals: 2,
        basis: "node_interval",
      },
      {
        phase: "reviewer",
        seconds: null,
        completed_intervals: 2,
        measured_intervals: 1,
        basis: "node_interval",
      },
    ],
  };
  await page.route(`**/api/runs/${completed.id}/metrics`, (route) =>
    route.fulfill({ json: data }),
  );
  await page.getByText("模型、用量与耗时", { exact: true }).click();
  const panel = page.getByRole("region", { name: "任务统计" });
  await expect(panel).toContainText("USD 0.0120000（已知部分；总量 Unknown）");
  const models = panel.getByRole("table", { name: "模型用量" });
  await expect(models).toContainText("openai/DEMO-configured");
  await expect(models).toContainText("DEMO-returned");
  await expect(panel.getByLabel("阶段耗时")).toContainText("检索：3.00 秒");
  await expect(panel.getByLabel("阶段耗时")).toContainText("校验：Unknown");
  await models.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: test.info().outputPath("run-metrics.png"),
    fullPage: true,
  });
});

test("MOCK cancelled task can refresh a late persisted charge while retaining cancellation", async ({
  page,
}) => {
  await show(page, "cancelled");
  let late = false;
  await page.route(`**/api/runs/${completed.id}/metrics`, (route) =>
    route.fulfill({
      json: {
        ...snapshot("cancelled"),
        known_estimate_usd: late ? 0.2 : null,
        estimate_complete: late,
      },
    }),
  );
  await page.getByText("模型、用量与耗时", { exact: true }).click();
  const panel = page.getByRole("region", { name: "任务统计" });
  await expect(panel).toContainText("SDK 费用估算Unknown");
  late = true;
  await panel.getByRole("button", { name: "刷新任务统计" }).click();
  await expect(panel).toContainText("USD 0.200000");
  await expect(panel).toContainText("已取消");
  await expect(panel).toContainText("精确服务商账单Unknown");
});

test("MOCK active statistics poll only while expanded and preserve the SSE-owned running state", async ({
  page,
}) => {
  await page.clock.install();
  const chat = await show(page, "running");
  let reads = 0;
  await page.route(`**/api/runs/${completed.id}/metrics`, (route) => {
    reads++;
    return route.fulfill({ json: snapshot("running") });
  });
  await page.getByText("模型、用量与耗时", { exact: true }).click();
  await expect.poll(() => reads).toBe(1);
  await expect(page.getByRole("region", { name: "任务统计" })).toContainText(
    "截至本次读取",
  );
  await page.clock.runFor(5001);
  await expect.poll(() => reads).toBe(2);
  await page.getByText("模型、用量与耗时", { exact: true }).click();
  await page.clock.runFor(10001);
  expect(reads).toBe(2);
  expect(chat.runs.get(completed.id)?.status).toBe("running");
  await expect(
    page.getByRole("heading", { name: "执行中", exact: true }),
  ).toBeVisible();
});

test("MOCK mismatched or private error records never appear and failed polling can be recovered", async ({
  page,
}) => {
  await show(page, "completed");
  let step = 0;
  await page.route(`**/api/runs/${completed.id}/metrics`, (route) =>
    route.fulfill(
      step === 0
        ? {
            status: 503,
            json: { error_code: "request_failed", private: "PRIVATE_SECRET" },
          }
        : {
            json: {
              ...snapshot(),
              run_id:
                step === 1
                  ? "00000000-0000-4000-8000-000000000016"
                  : completed.id,
            },
          },
    ),
  );
  await page.getByText("模型、用量与耗时", { exact: true }).click();
  const panel = page.getByRole("region", { name: "任务统计" });
  await expect(panel.getByRole("alert")).toBeVisible();
  await expect(panel).not.toContainText("PRIVATE_SECRET");
  step = 1;
  await panel.getByRole("button", { name: "刷新任务统计" }).click();
  await expect(panel.getByRole("alert")).toContainText("不一致");
  await expect(panel).not.toContainText("SDK 费用估算");
  step = 2;
  await panel.getByRole("button", { name: "刷新任务统计" }).click();
  await expect(panel).toContainText("精确服务商账单Unknown");
  await expect(panel.getByRole("alert")).toHaveCount(0);
});
