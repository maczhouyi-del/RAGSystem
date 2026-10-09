import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { setupChat } from "./chat-fixtures";

// MOCK HTTP persistence/concurrency contracts; original byte integrity is tested
// separately with real PostgreSQL, not claimed from browser fixtures.
async function setup(page: Page, legacy = false) {
  await setupChat(page);
  const original = {
    kind: "arxiv_atom",
    captured_at: "2026-10-09T00:00:00Z",
    values: {
      title: "MOCK official title",
      authors: ["Alice"],
      year: 2024,
      venue: null,
    },
    pdf_sha256: "a".repeat(64),
    arxiv_id: "2408.09869v2",
    arxiv_family_id: "2408.09869",
    arxiv_version: 2,
    source_url: "https://arxiv.org/abs/2408.09869v2",
  };
  const state = {
    paper: {
      id: "MOCK-metadata-paper",
      title: "MOCK official title",
      authors: ["Alice"],
      year: 2024,
      venue: null as string | null,
      status: "indexed",
      error_code: null,
      chunk_count: 1,
      arxiv_id: "2408.09869v2",
      arxiv_family_id: "2408.09869",
      arxiv_version: 2,
      source_status: "unknown",
      original_metadata: legacy ? null : original,
      metadata_version: 1,
      overridden_fields: [] as string[],
    },
    fail: false,
    patches: [] as Record<string, unknown>[],
  };
  await page.route("**/api/papers/search?*", (route) => {
    const parameters = new URL(route.request().url()).searchParams;
    const title = parameters.get("title");
    const items =
      !title || state.paper.title.includes(title) ? [state.paper] : [];
    return route.fulfill({
      json: { items, total: items.length, limit: 50, offset: 0 },
    });
  });
  await page.route("**/api/papers/MOCK-metadata-paper", (route) => {
    if (route.request().method() === "GET")
      return route.fulfill({ json: state.paper });
    const patch = route.request().postDataJSON() as Record<string, unknown>;
    state.patches.push(patch);
    if (state.fail)
      return route.fulfill({
        status: 503,
        json: { error_code: "infrastructure_unavailable" },
      });
    if (patch.expected_metadata_version !== state.paper.metadata_version)
      return route.fulfill({
        status: 409,
        json: { error_code: "paper_metadata_conflict" },
      });
    state.paper = {
      ...state.paper,
      ...(patch.title === undefined ? {} : { title: String(patch.title) }),
      ...(patch.authors === undefined
        ? {}
        : { authors: patch.authors as string[] }),
      ...(patch.year === undefined ? {} : { year: patch.year as number }),
      ...(patch.venue === undefined
        ? {}
        : { venue: patch.venue as string | null }),
      metadata_version: state.paper.metadata_version + 1,
      overridden_fields: ["title", "authors", "year", "venue"],
    };
    return route.fulfill({ json: state.paper });
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Knowledge Base", exact: true })
    .click();
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await page
    .getByRole("button", {
      name: "编辑 MOCK official title 元数据",
      exact: true,
    })
    .click();
  return state;
}

test("metadata edits save and survive reload while original source/version stays visible", async ({
  page,
}) => {
  const state = await setup(page);
  const editor = page.getByRole("form", { name: "编辑论文元数据" });
  await editor
    .getByText("导入时的元数据：arXiv 返回值", { exact: true })
    .click();
  await expect(editor.getByText(/原始标题：MOCK official title/)).toBeVisible();
  await expect(editor).toContainText("原始 arXiv 标识：2408.09869v2；版本：2");
  await editor
    .getByLabel("编辑标题", { exact: true })
    .fill("MOCK user correction");
  await editor.getByLabel("编辑作者", { exact: true }).fill("Carol; Dave");
  await editor.getByLabel("编辑年份", { exact: true }).fill("2025");
  await editor.getByLabel("编辑会议/期刊", { exact: true }).fill("MOCK venue");
  await page.screenshot({
    path: test.info().outputPath("metadata-edit.png"),
    fullPage: true,
  });
  await editor.getByRole("button", { name: "保存元数据", exact: true }).click();
  await expect(editor).toHaveCount(0);
  expect(state.patches).toEqual([
    {
      title: "MOCK user correction",
      authors: ["Carol", "Dave"],
      year: 2025,
      venue: "MOCK venue",
      expected_metadata_version: 1,
    },
  ]);
  await expect(
    page.getByRole("link", { name: "MOCK user correction", exact: true }),
  ).toHaveAttribute("href", "/api/papers/MOCK-metadata-paper/pdf");
  await expect(page.locator("tbody tr")).toContainText("人工维护字段");
  expect(state.paper.original_metadata?.values.title).toBe(
    "MOCK official title",
  );
  expect(state.paper.arxiv_version).toBe(2);
  await page.reload();
  await expect(
    page.getByRole("link", { name: "MOCK user correction", exact: true }),
  ).toBeVisible();
  await expect(page.locator("tbody tr")).toContainText("Carol; Dave");
});

test("failed edits retain draft and existing data across library filtering and can retry", async ({
  page,
}) => {
  const state = await setup(page);
  state.fail = true;
  const editor = page.getByRole("form", { name: "编辑论文元数据" });
  await editor
    .getByLabel("编辑标题", { exact: true })
    .fill("MOCK retained draft");
  await editor.getByRole("button", { name: "保存元数据", exact: true }).click();
  await expect(editor.getByRole("alert")).toContainText("HTTP 503");
  await expect(editor.getByLabel("编辑标题", { exact: true })).toHaveValue(
    "MOCK retained draft",
  );
  expect(state.paper.title).toBe("MOCK official title");
  await page.getByLabel("搜索论文标题", { exact: true }).fill("missing");
  await page.getByRole("button", { name: "搜索文献", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(0);
  await expect(editor.getByLabel("编辑标题", { exact: true })).toHaveValue(
    "MOCK retained draft",
  );
  state.fail = false;
  await editor.getByRole("button", { name: "保存元数据", exact: true }).click();
  await expect(editor).toHaveCount(0);
  expect(state.paper.title).toBe("MOCK retained draft");
  await page.getByRole("button", { name: "清除筛选", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "MOCK retained draft", exact: true }),
  ).toBeVisible();
});

test("stale edit cannot overwrite a concurrent update and explicit reload replaces draft", async ({
  page,
}) => {
  const state = await setup(page);
  const editor = page.getByRole("form", { name: "编辑论文元数据" });
  await editor.getByLabel("编辑标题", { exact: true }).fill("MOCK stale draft");
  state.paper = {
    ...state.paper,
    title: "MOCK external correction",
    metadata_version: 2,
  };
  await editor.getByRole("button", { name: "保存元数据", exact: true }).click();
  await expect(editor.getByRole("alert")).toContainText(
    "paper_metadata_conflict",
  );
  await expect(editor.getByLabel("编辑标题", { exact: true })).toHaveValue(
    "MOCK stale draft",
  );
  await expect(
    editor.getByRole("button", { name: "保存元数据", exact: true }),
  ).toBeDisabled();
  expect(state.paper.title).toBe("MOCK external correction");
  await editor
    .getByRole("button", { name: "载入最新内容并替换草稿", exact: true })
    .click();
  await expect(editor.getByLabel("编辑标题", { exact: true })).toHaveValue(
    "MOCK external correction",
  );
  await expect(
    editor.getByRole("button", { name: "保存元数据", exact: true }),
  ).toBeEnabled();
  await editor.getByLabel("编辑作者", { exact: true }).fill("Reviewed author");
  await editor.getByRole("button", { name: "保存元数据", exact: true }).click();
  await expect(editor).toHaveCount(0);
  expect(state.patches.at(-1)?.expected_metadata_version).toBe(2);
  expect(state.paper.title).toBe("MOCK external correction");
  expect(state.paper.original_metadata?.arxiv_version).toBe(2);
});

test("legacy original is explicitly unknown and cancel leaves all data unchanged", async ({
  page,
}) => {
  const state = await setup(page, true);
  const editor = page.getByRole("form", { name: "编辑论文元数据" });
  await editor.getByText("导入时的元数据：未保存", { exact: true }).click();
  await expect(editor.getByText(/旧记录未保存导入时的元数据/)).toBeVisible();
  await editor
    .getByLabel("编辑标题", { exact: true })
    .fill("MOCK cancelled draft");
  await editor.getByRole("button", { name: "取消编辑", exact: true }).click();
  await expect(editor).toHaveCount(0);
  expect(state.patches).toEqual([]);
  expect(state.paper.title).toBe("MOCK official title");
  expect(state.paper.original_metadata).toBeNull();
});
