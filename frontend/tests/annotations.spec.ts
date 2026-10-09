import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { setupChat } from "./chat-fixtures";

// MOCK HTTP contract only; real PostgreSQL fixtures exercise incomplete coverage.
async function setup(page: Page, status = "partial") {
  await setupChat(page);
  const paper = {
    id: randomUUID(),
    title: "MOCK annotation paper",
    authors: [],
    year: 2024,
    venue: null,
    status: "indexed",
    chunk_count: 2,
    error_code: null,
  };
  const chunk = randomUUID(),
    entity = randomUUID();
  const state = {
    fail: false,
    seen: [] as string[],
    coverage: [] as Record<string, unknown>[],
    matches: 0,
  };
  await page.route("**/api/papers/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    state.seen.push(path);
    if (path === "/api/papers/search") {
      await route.fulfill({
        json: { items: [paper], total: 1, limit: 50, offset: 0 },
      });
      return;
    }
    if (path.endsWith("/annotations")) {
      if (state.fail) {
        await route.fulfill({
          status: 503,
          json: { error_code: "database_unavailable" },
        });
        return;
      }
      await route.fulfill({
        json: {
          paper_id: paper.id,
          status,
          total_chunks: 2,
          reviewed_chunks:
            status === "completed" ? 2 : status === "partial" ? 1 : 0,
          linked_chunks: status === "unprocessed" ? 0 : 1,
          active_chunks: status === "processing" ? 1 : 0,
          failed_chunks: status === "failed" ? 1 : 0,
          items:
            status === "unprocessed"
              ? []
              : [
                  {
                    entity_id: entity,
                    name: "DEMO dataset",
                    entity_type: "dataset",
                    chunk_id: chunk,
                    section_path: "Methods",
                    page_start: 2,
                    page_end: 3,
                  },
                ],
          total_occurrences: status === "unprocessed" ? 0 : 1,
          limit: 50,
          offset: 0,
        },
      });
      return;
    }
    if (path.endsWith("/source")) {
      await route.fulfill({
        json: {
          paper_id: paper.id,
          chunk_id: chunk,
          section_id: randomUUID(),
          section_path: "Methods",
          page_start: 2,
          page_end: 3,
          content: "SYNTHETIC ONLY: exact source fragment with DEMO dataset.",
        },
      });
      return;
    }
    await route.fulfill({ status: 404, json: { error_code: "not_found" } });
  });
  await page.route("**/api/annotations/coverage", async (route) => {
    state.coverage.push(route.request().postDataJSON());
    await route.fulfill({
      json: {
        total_chunks: 2,
        reviewed_chunks: 1,
        linked_chunks: 1,
        active_chunks: 0,
        failed_chunks: 0,
        matching_chunks: state.matches,
        strict: true,
        complete: false,
      },
    });
  });
  return state;
}

for (const [status, label] of [
  ["unprocessed", "未处理"],
  ["processing", "处理中"],
  ["partial", "部分完成"],
  ["completed", "完成"],
  ["failed", "失败"],
]) {
  test(`MOCK annotation ${status} is distinct from ingestion`, async ({
    page,
  }, testInfo) => {
    const state = await setup(page, status);
    await page.goto("/#/knowledge");
    const panel = page.locator("details").filter({
      has: page.locator("summary", {
        hasText: "MOCK annotation paper 实体标注",
      }),
    });
    await expect(panel.locator("summary")).toContainText("状态未读取");
    expect(state.seen.some((path) => path.endsWith("/annotations"))).toBe(
      false,
    );
    await panel.locator("summary").click();
    await expect(panel.locator("summary")).toContainText(`实体标注：${label}`);
    await expect(panel).toContainText(
      status === "completed"
        ? "审阅覆盖完成不代表提取准确"
        : "没有标注不代表论文没有相应实体",
    );
    if (status !== "unprocessed") {
      await panel
        .getByRole("button", { name: "查看 DEMO dataset 来源片段" })
        .click();
      await expect(panel.getByLabel("实体来源片段")).toContainText(
        "SYNTHETIC ONLY: exact source fragment",
      );
      await expect(panel.getByLabel("实体来源片段")).toContainText("p.2–3");
      if (status === "partial")
        await page.screenshot({
          path: testInfo.outputPath("annotation-partial-source.png"),
          fullPage: true,
        });
    } else await expect(panel).toContainText("不能据此判断原文不存在实体");
  });
}

test("MOCK failed status read is unknown and explicitly refreshable", async ({
  page,
}) => {
  const state = await setup(page);
  state.fail = true;
  await page.goto("/#/knowledge");
  const panel = page.locator("details").filter({
    has: page.locator("summary", {
      hasText: "MOCK annotation paper 实体标注",
    }),
  });
  await panel.locator("summary").click();
  await expect(panel.getByRole("alert")).toContainText("状态未知");
  await expect(panel.locator("summary")).toContainText("状态未读取");
  state.fail = false;
  await panel.getByRole("button", { name: "刷新实体标注" }).click();
  await expect(panel.locator("summary")).toContainText("部分完成");
});

test("MOCK strict filter warns about partial corpus and does not relax constraints", async ({
  page,
}) => {
  const state = await setup(page);
  await page.goto("/");
  await page
    .getByText("文献过滤条件（同字段 OR，不同字段 AND）", { exact: true })
    .click();
  await page.getByLabel("datasets", { exact: true }).fill("DEMO missing");
  const notice = page.getByLabel("实体过滤语义");
  await expect(notice).toContainText("当前严格实体过滤不可满足");
  await expect(notice).toContainText("未标注不代表不存在");
  expect(state.coverage.at(-1)?.datasets).toEqual(["DEMO missing"]);
  await expect(page.getByLabel("datasets", { exact: true })).toHaveValue(
    "DEMO missing",
  );
  await page.getByLabel("datasets", { exact: true }).fill("");
  await expect(notice).not.toContainText("当前严格实体过滤不可满足");
  await expect(notice).toContainText("不是全文搜索");
  // Old deadline must not later replace a successful read with a false timeout.
  await page.getByLabel("datasets", { exact: true }).fill("DEMO missing");
  await expect(notice).toContainText("当前严格实体过滤不可满足");
  await page.clock.install();
  await page.clock.fastForward(11000);
  await expect(notice).not.toContainText("读取超时");
});

test("MOCK matching strict filter still warns about unreviewed chunks", async ({
  page,
}) => {
  const state = await setup(page);
  state.matches = 1;
  await page.goto("/");
  await page
    .getByText("文献过滤条件（同字段 OR，不同字段 AND）", { exact: true })
    .click();
  await page.getByLabel("datasets", { exact: true }).fill("DEMO dataset");
  const notice = page.getByLabel("实体过滤语义");
  await expect(notice).toContainText("严格匹配 1 个");
  await expect(notice).toContainText("过滤结果不能视为完整");
  await expect(notice).not.toContainText("不可满足");
});

test("MOCK unavailable source shows no cached original fragment", async ({
  page,
}) => {
  await setup(page);
  await page.route("**/api/papers/*/chunks/*/source", (route) =>
    route.fulfill({ status: 410, json: { error_code: "source_deleted" } }),
  );
  await page.goto("/#/knowledge");
  const panel = page.locator("details").filter({
    has: page.locator("summary", {
      hasText: "MOCK annotation paper 实体标注",
    }),
  });
  await panel.locator("summary").click();
  await panel
    .getByRole("button", { name: "查看 DEMO dataset 来源片段" })
    .click();
  await expect(panel.getByRole("alert")).toContainText("来源读取失败或已移除");
  await expect(panel.getByLabel("实体来源片段")).toHaveCount(0);
});
