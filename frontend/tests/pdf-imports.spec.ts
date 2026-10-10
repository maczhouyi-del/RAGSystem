import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { createHash, randomUUID } from "node:crypto";
import { setupChat } from "./chat-fixtures";

// MOCK HTTP only; actual byte deduplication and concurrent retry invariants are
// independently exercised with real PostgreSQL. No parser/model benchmark claim.
function file(name: string, body = name) {
  return {
    name,
    mimeType: "application/pdf",
    buffer: Buffer.from(`%PDF-1.4 MOCK ${body}`),
  };
}
type PaperData = {
  id: string;
  title: string;
  authors: string[];
  year: number | null;
  venue: string | null;
  status: string;
  error_code: string | null;
  chunk_count: number;
  latest_ingestion_run_id: string;
};
type RunData = {
  id: string;
  kind: string;
  status: string;
  trace_id: string;
  error_code: string | null;
  result: { paper_id: string } | null;
};
async function setup(page: Page) {
  await setupChat(page);
  const papers = new Map<string, PaperData>(),
    runs = new Map<string, RunData>(),
    hashes = new Map<string, string>();
  const state = {
    uploads: [] as {
      name: string;
      title: string;
      authors: string;
      year: string;
      venue: string;
    }[],
    active: 0,
    maxActive: 0,
    failName: "",
    loseName: "",
    loseRetry: false,
    retries: 0,
    hold: null as Promise<void> | null,
    holdsByName: new Map<string, Promise<void>>(),
  };
  await page.route("**/api/papers/*", (route) => {
    const id = new URL(route.request().url()).pathname.split("/")[3];
    return route.fulfill({
      status: papers.has(id) ? 200 : 404,
      json: papers.get(id) ?? { error_code: "paper_not_found" },
    });
  });
  await page.route("**/api/papers/search?*", (route) =>
    route.fulfill({
      json: {
        items: [...papers.values()],
        total: papers.size,
        limit: 50,
        offset: 0,
      },
    }),
  );
  await page.route("**/api/runs/*", (route) => {
    const id = new URL(route.request().url()).pathname.split("/")[3];
    return route.fulfill({
      status: runs.has(id) ? 200 : 404,
      json: runs.get(id) ?? { error_code: "run_not_found" },
    });
  });
  await page.route("**/api/papers/upload", async (route) => {
    const raw = route.request().postDataBuffer()!.toString("utf8");
    const name =
      raw.match(/name="file"; filename="([^"]+)"/)?.[1] ?? "unknown.pdf";
    const field = (key: string) =>
      raw.match(new RegExp(`name="${key}"\\r\\n\\r\\n([^\\r]*)`))?.[1] ?? "";
    const metadata = {
      name,
      title: field("title"),
      authors: field("authors"),
      year: field("year"),
      venue: field("venue"),
    };
    state.uploads.push(metadata);
    state.active += 1;
    state.maxActive = Math.max(state.maxActive, state.active);
    try {
      if (state.hold) await state.hold;
      const namedHold = state.holdsByName.get(name);
      if (namedHold) await namedHold;
      if (name === state.failName)
        return route.fulfill({
          status: 503,
          json: { error_code: "infrastructure_unavailable" },
        });
      const bytes = raw.match(/%PDF-[\s\S]*?(?=\r\n--)/)?.[0] ?? "";
      const hash = createHash("sha256").update(bytes).digest("hex");
      const existing = hashes.get(hash);
      let paper: PaperData;
      if (existing) paper = papers.get(existing)!;
      else {
        const id = randomUUID(),
          runId = randomUUID();
        paper = {
          id,
          title: metadata.title || name,
          authors: metadata.authors ? metadata.authors.split(";") : [],
          year: metadata.year ? Number(metadata.year) : null,
          venue: metadata.venue || null,
          status: "queued",
          error_code: null,
          chunk_count: 0,
          latest_ingestion_run_id: runId,
        };
        papers.set(id, paper);
        hashes.set(hash, id);
        runs.set(runId, {
          id: runId,
          kind: "ingestion",
          status: "queued",
          trace_id: "MOCK-trace",
          error_code: null,
          result: null,
        });
      }
      if (name === state.loseName) {
        state.loseName = "";
        return route.abort("failed");
      }
      return route.fulfill({
        status: 202,
        json: {
          ...runs.get(paper.latest_ingestion_run_id),
          paper_id: paper.id,
          reused_existing: Boolean(existing),
        },
      });
    } finally {
      state.active -= 1;
    }
  });
  await page.route("**/api/papers/*/retry", (route) => {
    expect(route.request().method()).toBe("POST");
    expect(route.request().postDataJSON()).toEqual({});
    state.retries += 1;
    const id = new URL(route.request().url()).pathname.split("/")[3];
    const paper = papers.get(id)!;
    let run = runs.get(paper.latest_ingestion_run_id)!;
    if (run.status === "failed") {
      const runId = randomUUID();
      run = {
        ...run,
        id: runId,
        status: "queued",
        error_code: null,
        result: null,
      };
      runs.set(runId, run);
      paper.latest_ingestion_run_id = runId;
      paper.status = "queued";
      paper.error_code = null;
    }
    if (state.loseRetry) {
      state.loseRetry = false;
      return route.abort("failed");
    }
    return route.fulfill({ status: 202, json: run });
  });
  function complete(title?: string) {
    for (const paper of papers.values())
      if (!title || paper.title === title) {
        paper.status = "indexed";
        paper.chunk_count = 3;
        const run = runs.get(paper.latest_ingestion_run_id)!;
        run.status = "completed";
        run.result = { paper_id: paper.id };
      }
  }
  function fail(title: string) {
    const paper = [...papers.values()].find((paper) => paper.title === title)!;
    paper.status = "failed";
    paper.error_code = "embedding_failed";
    const run = runs.get(paper.latest_ingestion_run_id)!;
    run.status = "failed";
    run.error_code = "embedding_failed";
    return run.id;
  }
  await page.goto("/#/knowledge");
  return { state, papers, runs, complete, fail };
}
const progress = (page: Page) =>
  page.getByRole("region", { name: "PDF 导入进度", exact: true });
const row = (page: Page, name: string) =>
  page
    .getByRole("table", { name: "逐篇 PDF 导入", exact: true })
    .locator("tbody tr")
    .filter({ hasText: name });
async function submit(page: Page, files: ReturnType<typeof file>[]) {
  await page.getByLabel("PDF", { exact: true }).setInputFiles(files);
  await page
    .getByRole("button", { name: "上传并建立索引", exact: true })
    .click();
}

test("multiple PDFs use two upload slots, preserve pending files and show upload separately from indexing", async ({
  page,
}) => {
  const { state, complete } = await setup(page);
  const releases = new Map<string, () => void>();
  for (const name of ["a.pdf", "b.pdf", "c.pdf", "d.pdf"])
    state.holdsByName.set(
      name,
      new Promise<void>((resolve) => releases.set(name, resolve)),
    );
  await submit(page, [
    file("a.pdf"),
    file("b.pdf"),
    file("c.pdf"),
    file("d.pdf"),
  ]);
  await expect.poll(() => state.uploads.length).toBe(2);
  await expect(progress(page)).toContainText("等待上传 2 项 · 上传中 2 项");
  expect(state.maxActive).toBe(2);
  // Two independent requests may arrive in either order. Assert exact admission
  // membership, then release one slot at a time to test pending FIFO explicitly.
  expect(state.uploads.map((item) => item.name).sort()).toEqual([
    "a.pdf",
    "b.pdf",
  ]);
  await expect(
    page
      .getByRole("table", { name: "逐篇 PDF 导入", exact: true })
      .locator("tbody tr td:first-child"),
  ).toHaveText(["a.pdf", "b.pdf", "c.pdf", "d.pdf"]);
  releases.get("a.pdf")!();
  await expect.poll(() => state.uploads.length).toBe(3);
  expect(state.uploads[2].name).toBe("c.pdf");
  await expect(progress(page)).toContainText("等待上传 1 项 · 上传中 2 项");
  releases.get("b.pdf")!();
  await expect.poll(() => state.uploads.length).toBe(4);
  expect(state.uploads[3].name).toBe("d.pdf");
  releases.get("c.pdf")!();
  releases.get("d.pdf")!();
  await expect(progress(page)).toContainText("解析/索引中 4 项");
  await expect(progress(page)).toContainText("已索引 0 项");
  expect([
    ...state.uploads
      .slice(0, 2)
      .map((item) => item.name)
      .sort(),
    ...state.uploads.slice(2).map((item) => item.name),
  ]).toEqual(["a.pdf", "b.pdf", "c.pdf", "d.pdf"]);
  expect(state.maxActive).toBeLessThanOrEqual(2);
  complete();
  await progress(page).getByRole("button", { name: "刷新导入状态" }).click();
  await expect(progress(page)).toContainText("已索引 4 项");
  await page.screenshot({
    path: test.info().outputPath("batch-imports.png"),
    fullPage: true,
  });
});

test("byte-identical PDFs with different names reuse one server paper and Run", async ({
  page,
}) => {
  const { state, papers, runs } = await setup(page);
  await submit(page, [
    file("original.pdf", "same bytes"),
    file("renamed.pdf", "same bytes"),
  ]);
  await expect(progress(page)).toContainText("复用已有文献 1 项");
  await expect(row(page, "renamed.pdf")).toContainText(
    "服务端按 PDF 内容识别重复",
  );
  expect(state.uploads).toHaveLength(2);
  expect(papers.size).toBe(1);
  expect(runs.size).toBe(1);
});

test("one upload failure preserves successful files and retries only the failed original", async ({
  page,
}) => {
  const { state, papers } = await setup(page);
  state.failName = "bad.pdf";
  await submit(page, [
    file("good.pdf"),
    file("bad.pdf"),
    file("also-good.pdf"),
  ]);
  await expect(progress(page)).toContainText("失败 1 项");
  await expect(row(page, "good.pdf").first()).toContainText("已接受上传");
  await expect(row(page, "bad.pdf").getByRole("alert")).toContainText(
    "数据库或 Redis 不可用",
  );
  expect(papers.size).toBe(2);
  state.failName = "";
  await row(page, "bad.pdf")
    .getByRole("button", { name: "核对并重试此文件上传" })
    .click();
  await expect(progress(page)).toContainText("解析/索引中 3 项");
  expect(
    state.uploads.map((item) => item.name).filter((name) => name === "bad.pdf"),
  ).toHaveLength(2);
  expect(state.uploads.filter((item) => item.name === "good.pdf")).toHaveLength(
    1,
  );
});

test("lost upload response keeps ambiguity visible and manual replay converges by PDF content", async ({
  page,
}) => {
  const { state, papers, runs } = await setup(page);
  state.loseName = "lost.pdf";
  await submit(page, [file("lost.pdf")]);
  await expect(row(page, "lost.pdf")).toContainText("上传结果待核对");
  expect(papers.size).toBe(1);
  expect(state.uploads).toHaveLength(1);
  await row(page, "lost.pdf")
    .getByRole("button", { name: "核对并重试此文件上传" })
    .click();
  await expect(row(page, "lost.pdf")).toContainText(
    "服务端按 PDF 内容识别重复",
  );
  expect(state.uploads).toHaveLength(2);
  expect(papers.size).toBe(1);
  expect(runs.size).toBe(1);
});

test("accepted ingestion status survives reload through ID-only read recovery", async ({
  page,
}) => {
  const { state, papers, complete } = await setup(page);
  await submit(page, [file("reload.pdf")]);
  await expect(row(page, "reload.pdf")).toContainText("已接受上传");
  const ids = await page.evaluate(() =>
    JSON.parse(localStorage.getItem("ragagent-import-status-ids-v1")!),
  );
  expect(Object.keys(ids[0]).sort()).toEqual(["paper_id", "run_id"]);
  expect(JSON.stringify(ids)).not.toContain("reload.pdf");
  complete();
  await page.reload();
  await expect(progress(page)).toContainText("已索引 1 项");
  expect(state.uploads).toHaveLength(1);
  expect(papers.size).toBe(1);
  expect(state.retries).toBe(0);
  await row(page, "reload.pdf")
    .getByText("查看索引结果", { exact: true })
    .click();
  await expect(row(page, "reload.pdf")).toContainText("文本块：3");
});

test("failed indexing retries the existing paper without reupload and preserves the old failed Run", async ({
  page,
}) => {
  const { state, papers, runs, fail, complete } = await setup(page);
  await submit(page, [file("index-fail.pdf"), file("other.pdf")]);
  await expect(progress(page)).toContainText("解析/索引中 2 项");
  const old = fail("index-fail.pdf");
  complete("other.pdf");
  await progress(page).getByRole("button", { name: "刷新导入状态" }).click();
  await expect(row(page, "index-fail.pdf")).toContainText("解析/索引失败");
  await row(page, "index-fail.pdf")
    .getByRole("button", { name: "重试此篇解析与索引" })
    .click();
  await expect(progress(page)).toContainText("解析/索引中 1 项");
  expect(state.retries).toBe(1);
  expect(state.uploads).toHaveLength(2);
  expect(papers.size).toBe(2);
  expect(runs.get(old)?.status).toBe("failed");
  expect(runs.size).toBe(3);
});

test("lost indexing retry response reads the latest Run reference instead of creating another job", async ({
  page,
}) => {
  const { state, papers, runs, fail } = await setup(page);
  await submit(page, [file("retry-lost.pdf")]);
  await expect(row(page, "retry-lost.pdf")).toContainText("已接受上传");
  const old = fail("retry-lost.pdf");
  await progress(page).getByRole("button", { name: "刷新导入状态" }).click();
  await expect(row(page, "retry-lost.pdf")).toContainText("解析/索引失败");
  state.loseRetry = true;
  await row(page, "retry-lost.pdf")
    .getByRole("button", { name: "重试此篇解析与索引" })
    .click();
  await expect(progress(page)).toContainText("解析/索引中 1 项");
  const latest = [...papers.values()][0].latest_ingestion_run_id;
  expect(latest).not.toBe(old);
  await row(page, "retry-lost.pdf")
    .getByText("查看索引结果", { exact: true })
    .click();
  await expect(row(page, "retry-lost.pdf")).toContainText(latest);
  expect(state.retries).toBe(1);
  expect(runs.size).toBe(2);
  expect(state.uploads).toHaveLength(1);
});

test("single PDF metadata remains supported while batch titles stay per-file", async ({
  page,
}) => {
  const { state, papers } = await setup(page);
  const form = page.getByRole("form", { name: "PDF 导入", exact: true });
  await form.getByLabel("标题", { exact: true }).fill("MOCK custom title");
  await form.getByLabel("作者（分号分隔）").fill("Alice;Bob");
  await form.getByLabel("年份", { exact: true }).fill("2024");
  await form.getByLabel("会议 / 期刊", { exact: true }).fill("MOCK venue");
  await submit(page, [file("single.pdf")]);
  await expect(row(page, "single.pdf")).toContainText("已接受上传");
  expect(state.uploads[0]).toEqual({
    name: "single.pdf",
    title: "MOCK custom title",
    authors: "Alice;Bob",
    year: "2024",
    venue: "MOCK venue",
  });
  await submit(page, [file("many-a.pdf"), file("many-b.pdf")]);
  await expect(progress(page)).toContainText("解析/索引中 3 项");
  expect(state.uploads.slice(1).every((item) => item.title === "")).toBe(true);
  expect([...papers.values()].map((paper) => paper.title)).toEqual([
    "MOCK custom title",
    "many-a.pdf",
    "many-b.pdf",
  ]);
});

test("dragged files remain unsubmitted until explicit start, invalid PDF does not block a valid one", async ({
  page,
}) => {
  const { state } = await setup(page);
  await page
    .getByLabel("拖拽 PDF 文件区域", { exact: true })
    .evaluate((node) => {
      const transfer = new DataTransfer();
      transfer.items.add(
        new File(["%PDF-1.4 MOCK drag"], "drag.pdf", {
          type: "application/pdf",
        }),
      );
      transfer.items.add(
        new File(["invalid"], "not-pdf.pdf", { type: "application/pdf" }),
      );
      node.dispatchEvent(
        new DragEvent("drop", { bubbles: true, dataTransfer: transfer }),
      );
    });
  await expect(
    page.getByText("已选择 2 个文件；尚未上传。", { exact: true }),
  ).toBeVisible();
  expect(state.uploads).toHaveLength(0);
  await page.getByRole("button", { name: "上传并建立索引" }).click();
  await expect(row(page, "drag.pdf")).toContainText("已接受上传");
  await expect(row(page, "not-pdf.pdf").getByRole("alert")).toContainText(
    "有效的 PDF 标识",
  );
  expect(state.uploads).toHaveLength(1);
});
