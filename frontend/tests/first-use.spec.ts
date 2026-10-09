import { expect, test } from "@playwright/test";
import type { Page, Route } from "@playwright/test";
import { run, setupChat } from "./chat-fixtures";

// MOCK HTTP/SSE state: UI workflow and persistence contracts, not real parsing,
// inference, scientific quality or Windows Credential Manager evidence.
async function setupGuide(page: Page, existing = false) {
  const chat = await setupChat(page);
  const fixture = {
    authorized: existing,
    initialized: existing,
    modelsConfigured: existing,
    indexed: existing,
    offline: false,
    database: "available",
    workers: 1,
    paidTests: 0,
    writes: [] as string[],
    papers: existing ? [paper("indexed")] : ([] as ReturnType<typeof paper>[]),
  };
  const token = "SYNTHETIC_TEST_CREDENTIAL".repeat(3);
  page.on("request", (request) => {
    if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method())) {
      fixture.writes.push(new URL(request.url()).pathname);
    }
  });
  await page.route("**/api/health", (route) =>
    route.fulfill({
      status: fixture.offline ? 503 : 200,
      json: fixture.offline ? {} : { status: "ok" },
    }),
  );
  await page.route("**/api/auth/status", (route) =>
    route.fulfill({
      json: {
        initialized: fixture.initialized,
        authenticated: fixture.authorized,
      },
    }),
  );
  await page.route("**/api/auth/session", (route) => {
    fixture.authorized =
      route.request().headers().authorization === `Bearer ${token}`;
    fixture.initialized = fixture.authorized;
    return route.fulfill({
      status: fixture.authorized ? 200 : 401,
      json: { authenticated: fixture.authorized },
    });
  });
  await page.route("**/api/conversations*", async (route) => {
    if (fixture.authorized) await route.fallback();
    else
      await route.fulfill({
        status: 401,
        json: { error_code: "local_auth_required" },
      });
  });
  await page.route("**/api/diagnostics", (route) =>
    route.fulfill({
      json: {
        build: {
          version: "0.2.0",
          source_commit: "unknown",
          dirty: null,
          built_at_utc: "unknown",
        },
        database: fixture.database,
        redis: "available",
        local_auth: "initialized",
        inference: "not_tested",
        queues: Object.fromEntries(
          ["interactive", "ingestion", "evaluation"].map((role) => [
            role,
            { pending: 0, workers: fixture.workers },
          ]),
        ),
        chat_configuration: Object.fromEntries(
          ["supervisor", "retriever", "analyst", "reviewer"].map((role) => [
            role,
            { credential_configured: fixture.modelsConfigured },
          ]),
        ),
        retrieval_configuration: { model_loading: "not_tested" },
        corpus: {
          state: fixture.indexed ? "available" : "empty",
          usable_papers: fixture.indexed ? 1 : 0,
        },
        runtime_dependencies: {
          docling: "installed",
          local_models: "installed",
        },
      },
    }),
  );
  await page.route("**/api/providers", (route) =>
    route.fulfill({
      json: {
        agents: Object.fromEntries(
          ["supervisor", "retriever", "analyst", "reviewer"].map((role) => [
            role,
            {
              provider: "openai",
              model: "MOCK-only",
              api_base: null,
              api_key_env: "MOCK_KEY",
              key_configured: fixture.modelsConfigured,
            },
          ]),
        ),
      },
    }),
  );
  await page.route("**/api/providers/test", (route) => {
    fixture.paidTests++;
    return route.fulfill({ json: { ok: true, model: "MOCK-only" } });
  });
  await page.route("**/api/papers/search?*", (route) =>
    route.fulfill({
      json: {
        items: fixture.papers,
        total: fixture.papers.length,
        limit: 50,
        offset: 0,
      },
    }),
  );
  await page.route("**/api/papers/upload", (route) => {
    fixture.papers = [paper("queued")];
    return route.fulfill({ status: 202, json: { ...run, kind: "ingestion" } });
  });
  return { fixture, token, chat };
}
function paper(status: string) {
  return {
    id: "MOCK-paper",
    title: "MOCK first paper",
    authors: [],
    year: null,
    venue: null,
    status,
    error_code: null,
    chunk_count: status === "indexed" ? 1 : 0,
  };
}

test("blank user follows authorization, model check, upload, index and first question without implicit paid tests", async ({
  page,
}) => {
  const { fixture, token, chat } = await setupGuide(page);
  await page.goto("/");
  const guide = page.getByRole("region", { name: "首次使用引导" });
  await expect(guide).toBeVisible();
  await expect(guide.getByText(/后端尚未配对/)).toBeVisible();
  await expect(
    guide.getByRole("button", { name: "打开首次问答" }),
  ).toBeDisabled();
  await guide.getByRole("button", { name: "前往本机授权" }).click();
  await page.getByLabel("开发凭据").fill(token);
  await page.getByRole("button", { name: "连接并检查授权" }).click();
  await expect(guide.getByText("本机授权已通过")).toBeVisible();
  await expect(
    guide.getByText(/没有 API Key 也可以先做环境诊断/),
  ).toBeVisible();
  await guide.getByRole("button", { name: "检查模型设置" }).click();
  await expect(
    page.getByRole("heading", { name: "Provider Settings" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "连接测试（可能产生少量费用）" }),
  ).toHaveCount(4);
  // Simulates runtime credential configuration, never claims the UI saved keys.
  fixture.modelsConfigured = true;
  await guide.getByRole("button", { name: "刷新引导状态" }).click();
  await expect(
    guide.getByText("四个聊天角色已配置；真实推理尚未验证"),
  ).toBeVisible();
  await guide.getByRole("button", { name: "上传第一篇论文" }).click();
  await page.getByLabel("PDF", { exact: true }).setInputFiles({
    name: "fixture.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 MOCK UI upload only"),
  });
  await page.getByRole("button", { name: "上传并建立索引" }).click();
  await expect(page.locator("tbody")).toContainText("queued");
  await expect(
    guide.getByRole("button", { name: "打开首次问答" }),
  ).toBeDisabled();
  fixture.indexed = true;
  fixture.papers = [paper("indexed")];
  await guide.getByRole("button", { name: "刷新引导状态" }).click();
  await expect(guide.getByText("已有 1 篇可用文献")).toBeVisible();
  await guide.getByRole("button", { name: "打开首次问答" }).click();
  await page.getByLabel("研究问题").fill("MOCK question about this paper");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "已通过自动证据校验" }),
  ).toBeVisible();
  await page.screenshot({
    path: test.info().outputPath("first-use.png"),
    fullPage: true,
  });
  expect(chat.sends).toBe(1);
  expect(fixture.paidTests).toBe(0);
  expect(
    await page.evaluate(
      () => JSON.stringify(localStorage) + JSON.stringify(sessionStorage),
    ),
  ).not.toContain(token);
});

test("configured user keeps original interface and can reopen the guide without initialization writes", async ({
  page,
}) => {
  const { fixture, chat } = await setupGuide(page, true);
  chat.create("MOCK existing conversation");
  await page.goto("/");
  await expect(page.getByLabel("研究问题")).toBeVisible();
  await expect(page.getByRole("region", { name: "首次使用引导" })).toHaveCount(
    0,
  );
  await page.getByRole("button", { name: "首次使用引导", exact: true }).click();
  await expect(
    page.getByText("四个聊天角色已配置；真实推理尚未验证"),
  ).toBeVisible();
  expect(fixture.writes).toEqual([]);
  expect(chat.conversations.size).toBe(1);
  expect(fixture.paidTests).toBe(0);
});

test("dismiss and restart preserves papers, conversations and memory; guide remains available", async ({
  page,
}) => {
  const { fixture, chat } = await setupGuide(page, true);
  const conversation = chat.create("MOCK saved conversation");
  chat.memories.set(conversation.id, [
    { id: "MOCK-memory", note: "Keep this memory" },
  ]);
  await page.goto("/");
  await page.getByRole("button", { name: "首次使用引导", exact: true }).click();
  await page.getByRole("button", { name: "关闭引导" }).click();
  await page.reload();
  await expect(page.getByRole("region", { name: "首次使用引导" })).toHaveCount(
    0,
  );
  await expect(page.getByLabel("研究问题")).toBeVisible();
  await page.getByRole("button", { name: "首次使用引导", exact: true }).click();
  await expect(page.getByText("已有 1 篇可用文献")).toBeVisible();
  expect(fixture.papers).toEqual([paper("indexed")]);
  expect(chat.conversations.get(conversation.id)?.title).toBe(
    "MOCK saved conversation",
  );
  expect(chat.memories.get(conversation.id)).toEqual([
    { id: "MOCK-memory", note: "Keep this memory" },
  ]);
  expect(fixture.writes).toEqual([]);
});

test("dismissed empty environment stays dismissed after restart and can be reopened", async ({
  page,
}) => {
  const { fixture } = await setupGuide(page);
  fixture.authorized = fixture.initialized = true;
  await page.goto("/");
  await expect(
    page.getByRole("region", { name: "首次使用引导" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "关闭引导" }).click();
  await page.reload();
  await expect(page.getByRole("region", { name: "首次使用引导" })).toHaveCount(
    0,
  );
  await page.getByRole("button", { name: "首次使用引导", exact: true }).click();
  await expect(
    page.getByText(/尚无可用文献：上传成功不代表索引完成/),
  ).toBeVisible();
  expect(fixture.writes).toEqual([]);
});

test("offline backend shows recovery and then recovers without resetting data", async ({
  page,
}) => {
  const { fixture } = await setupGuide(page, true);
  fixture.offline = true;
  await page.goto("/");
  const guide = page.getByRole("region", { name: "首次使用引导" });
  await expect(guide.getByText(/先启动 Docker Desktop/)).toBeVisible();
  await expect(
    guide.getByRole("button", { name: "打开首次问答" }),
  ).toBeDisabled();
  fixture.offline = false;
  await guide.getByRole("button", { name: "刷新引导状态" }).click();
  await expect(
    guide.getByText("数据库、Redis 与问答/索引 worker 可用"),
  ).toBeVisible();
  await expect(
    guide.getByRole("button", { name: "打开首次问答" }),
  ).toBeEnabled();
  expect(fixture.writes).toEqual([]);
});

test("database or worker failure blocks first question independently of configured models", async ({
  page,
}) => {
  const { fixture } = await setupGuide(page, true);
  fixture.database = "unavailable";
  await page.goto("/");
  await page.getByRole("button", { name: "首次使用引导", exact: true }).click();
  const guide = page.getByRole("region", { name: "首次使用引导" });
  await expect(guide.getByText(/基础服务未就绪/)).toBeVisible();
  await expect(
    guide.getByRole("button", { name: "打开首次问答" }),
  ).toBeDisabled();
  fixture.database = "available";
  fixture.workers = 0;
  await guide.getByRole("button", { name: "刷新引导状态" }).click();
  await expect(
    guide.getByRole("button", { name: "打开首次问答" }),
  ).toBeDisabled();
  expect(fixture.paidTests).toBe(0);
  expect(fixture.writes).toEqual([]);
});

test("unresponsive backend times out without overlapping probes and offers recovery", async ({
  page,
}) => {
  test.setTimeout(25000);
  const { fixture } = await setupGuide(page, true);
  const pending: Route[] = [];
  const hang = (route: Route) => {
    pending.push(route);
  };
  await page.route("**/api/health", hang);
  await page.goto("/");
  await page.getByRole("button", { name: "首次使用引导", exact: true }).click();
  const guide = page.getByRole("region", { name: "首次使用引导" });
  await expect(
    guide.getByText(/后端不可用：先启动 Docker Desktop/),
  ).toBeVisible({ timeout: 15000 });
  await expect(
    guide.getByRole("button", { name: "刷新引导状态" }),
  ).toBeEnabled();
  await page.unroute("**/api/health", hang);
  for (const route of pending) await route.abort().catch(() => {});
  await guide.getByRole("button", { name: "刷新引导状态" }).click();
  await expect(
    guide.getByText("数据库、Redis 与问答/索引 worker 可用"),
  ).toBeVisible();
  expect(fixture.writes).toEqual([]);
});
