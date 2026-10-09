import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { run, setupChat } from "./chat-fixtures";

// MOCK HTTP contracts, not actual PostgreSQL/inference/scientific performance.
async function library(page: Page) {
  await setupChat(page);
  const papers = Array.from({ length: 214 }, (_, index) => ({
    id: `MOCK-paper-${index}`,
    title: `MOCK Science ${index}`,
    authors: index % 2 ? ["Alice DEMO"] : ["Bob DEMO"],
    year: 2020 + (index % 5),
    venue: index % 2 ? "Conference DEMO" : "Journal DEMO",
    status: index % 2 ? "indexed" : "queued",
    error_code: null,
    chunk_count: index % 2 ? 1 : 0,
  }));
  const state = {
    requests: [] as URLSearchParams[],
    fail: false,
    delayed: false,
  };
  await page.route("**/api/papers/search?*", async (route) => {
    const params = new URL(route.request().url()).searchParams;
    state.requests.push(params);
    if (state.fail) {
      await route.fulfill({
        status: 503,
        json: { error_code: "infrastructure_unavailable" },
      });
      return;
    }
    if (params.get("title") === "slow") {
      state.delayed = true;
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    let items = papers.filter(
      (paper) =>
        (!params.get("title") || paper.title.includes(params.get("title")!)) &&
        (!params.get("author") ||
          paper.authors.some((author) =>
            author.includes(params.get("author")!),
          )) &&
        (!params.get("year") || paper.year === Number(params.get("year"))) &&
        (!params.get("venue") || paper.venue.includes(params.get("venue")!)) &&
        (!params.get("status") || paper.status === params.get("status")),
    );
    if (params.get("sort") === "year")
      items = [...items].sort((a, b) =>
        params.get("direction") === "asc" ? a.year - b.year : b.year - a.year,
      );
    const offset = Number(params.get("offset")),
      limit = Number(params.get("limit"));
    await route.fulfill({
      json: {
        items: items.slice(offset, offset + limit),
        total: items.length,
        limit,
        offset,
      },
    });
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Knowledge Base", exact: true })
    .click();
  await expect(page.locator("tbody tr")).toHaveCount(50);
  return state;
}

test("search covers papers beyond the current page and sends all server filters", async ({
  page,
}) => {
  const state = await library(page);
  await expect(
    page.getByText("共 214 篇 · 第 1 / 5 页", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("搜索论文标题", { exact: true }).fill("Science 209");
  await page.getByLabel("搜索作者", { exact: true }).fill("Alice");
  await page.getByLabel("筛选论文年份", { exact: true }).fill("2024");
  await page.getByLabel("筛选会议或期刊", { exact: true }).fill("Conference");
  await page
    .getByLabel("筛选索引状态", { exact: true })
    .selectOption("indexed");
  await page.getByLabel("文献排序字段", { exact: true }).selectOption("year");
  await page.getByLabel("文献排序方向", { exact: true }).selectOption("asc");
  await page.getByRole("button", { name: "搜索文献", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await expect(
    page.getByRole("link", { name: "MOCK Science 209", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("共 1 篇 · 第 1 / 1 页", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "下一页", exact: true }),
  ).toBeDisabled();
  expect(Object.fromEntries(state.requests.at(-1)!)).toEqual({
    limit: "50",
    offset: "0",
    title: "Science 209",
    author: "Alice",
    year: "2024",
    venue: "Conference",
    status: "indexed",
    sort: "year",
    direction: "asc",
  });
  await page.screenshot({
    path: test.info().outputPath("library-search.png"),
    fullPage: true,
  });
});

test("filters reset paging, sorting and empty results remain counted and clearing recovers", async ({
  page,
}) => {
  const state = await library(page);
  await page.getByRole("button", { name: "下一页", exact: true }).click();
  await expect(
    page.getByText("共 214 篇 · 第 2 / 5 页", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("搜索作者", { exact: true }).fill("Alice");
  await page.getByLabel("文献排序字段", { exact: true }).selectOption("year");
  await page.getByLabel("文献排序方向", { exact: true }).selectOption("asc");
  await page.getByRole("button", { name: "搜索文献", exact: true }).click();
  await expect(
    page.getByText("共 107 篇 · 第 1 / 3 页", { exact: true }),
  ).toBeVisible();
  await expect(page.locator("tbody tr").first()).toContainText("2020");
  await page.getByRole("button", { name: "下一页", exact: true }).click();
  await expect(
    page.getByText("共 107 篇 · 第 2 / 3 页", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  await expect.poll(() => state.requests.at(-1)?.get("offset")).toBe("50");
  expect(state.requests.at(-1)?.get("author")).toBe("Alice");
  await page.getByLabel("搜索论文标题", { exact: true }).fill("missing");
  await page.getByRole("button", { name: "搜索文献", exact: true }).click();
  await expect(
    page.getByText("共 0 篇 · 第 1 / 1 页", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("没有符合筛选条件的文献。可清除筛选后重试。", {
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "清除筛选", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(50);
  await expect(
    page.getByText("共 214 篇 · 第 1 / 5 页", { exact: true }),
  ).toBeVisible();
  expect(state.requests.at(-1)?.has("title")).toBe(false);
});

test("late search cannot overwrite newer results and a failed refresh can recover", async ({
  page,
}) => {
  const state = await library(page);
  await page.getByLabel("搜索论文标题", { exact: true }).fill("slow");
  await page.getByRole("button", { name: "搜索文献", exact: true }).click();
  await expect.poll(() => state.delayed).toBe(true);
  await page.getByLabel("搜索论文标题", { exact: true }).fill("Science 209");
  await page.getByRole("button", { name: "搜索文献", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "MOCK Science 209", exact: true }),
  ).toBeVisible();
  await page.waitForTimeout(1100);
  await expect(page.locator("tbody tr")).toHaveCount(1);
  state.fail = true;
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("HTTP 503");
  await expect(
    page.getByRole("link", { name: "MOCK Science 209", exact: true }),
  ).toBeVisible();
  state.fail = false;
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(
    page.getByText("共 1 篇 · 第 1 / 1 页", { exact: true }),
  ).toBeVisible();
});

test("arxiv import still dispatches while a library filter is applied", async ({
  page,
}) => {
  await library(page);
  let submitted: unknown;
  await page.route("**/api/papers/arxiv", (route) => {
    submitted = route.request().postDataJSON();
    return route.fulfill({ status: 202, json: { ...run, kind: "arxiv" } });
  });
  await page.getByLabel("搜索作者", { exact: true }).fill("Alice");
  await page.getByRole("button", { name: "搜索文献", exact: true }).click();
  await expect(
    page.getByText("共 107 篇 · 第 1 / 3 页", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("arXiv ID", { exact: true }).fill("2408.09869v2");
  await page.getByRole("button", { name: "导入开放论文", exact: true }).click();
  await expect.poll(() => submitted).toEqual({ arxiv_id: "2408.09869v2" });
  await expect(page.getByText(/后台任务：/)).toBeVisible();
  await expect(page.getByLabel("搜索作者", { exact: true })).toHaveValue(
    "Alice",
  );
});
