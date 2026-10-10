import { createHash, randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { setupChat } from "./chat-fixtures";

// MOCK HTTP/UI contracts only. Extraction and persistence are tested against PostgreSQL/RQ.
async function setup(page: Page) {
  await setupChat(page);
  const pid = randomUUID(),
    cid = randomUUID(),
    rid = randomUUID();
  const content = "🧪 原文：科研数据集。Dataset: MNIST. Correction: NewMNIST.";
  const digest = createHash("sha256").update(content).digest("hex");
  const state = {
    writes: [] as {
      path: string;
      method: string;
      body: Record<string, unknown>;
    }[],
    mentions: [] as any[],
    linked: [] as any[],
    completed: false,
    failedRead: false,
    loseResponse: false,
    conflict: false,
  };
  await page.route("**/api/papers/**", async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      path = url.pathname;
    const method = req.method();
    if (method !== "GET")
      state.writes.push({ path, method, body: req.postDataJSON() });
    if (path === "/api/papers/search")
      return route.fulfill({
        json: {
          items: [
            {
              id: pid,
              title: "MOCK review paper",
              authors: [],
              year: 2024,
              venue: null,
              status: "indexed",
              chunk_count: 1,
              error_code: null,
            },
          ],
          total: 1,
          limit: 50,
          offset: 0,
        },
      });
    if (path.endsWith("/annotations"))
      return route.fulfill({
        json: {
          paper_id: pid,
          status: state.completed
            ? "completed"
            : state.mentions.length
              ? "partial"
              : "unprocessed",
          total_chunks: 1,
          reviewed_chunks: state.completed ? 1 : 0,
          linked_chunks: state.linked.length ? 1 : 0,
          active_chunks: 0,
          failed_chunks: 0,
          needs_review_chunks:
            state.mentions.length && !state.completed ? 1 : 0,
          items: [],
          total_occurrences: 0,
          limit: 50,
          offset: 0,
          latest_annotation_run_id: state.mentions.length ? rid : null,
          latest_annotation_run_status: state.mentions.length
            ? "completed"
            : null,
        },
      });
    if (path.endsWith("/annotation-chunks"))
      return route.fulfill({
        json: {
          items: [
            {
              chunk_id: cid,
              section_path: "Methods",
              page_start: 2,
              page_end: 3,
              content_sha256: digest,
              status: state.completed ? "completed" : "needs_review",
            },
          ],
          total: 1,
          limit: 50,
          offset: 0,
        },
      });
    if (path.endsWith("/source")) {
      if (state.failedRead)
        return route.fulfill({
          status: 410,
          json: { error_code: "source_deleted" },
        });
      return route.fulfill({
        json: {
          chunk_id: cid,
          section_path: "Methods",
          page_start: 2,
          page_end: 3,
          content,
          content_sha256: digest,
        },
      });
    }
    if (path.endsWith("/annotation-runs")) {
      const start = Array.from(
        content.slice(0, content.indexOf("MNIST")),
      ).length;
      state.mentions.push({
        id: randomUUID(),
        chunk_id: cid,
        name: "MNIST",
        entity_type: "dataset",
        span_start: start,
        span_end: start + 5,
        content_sha256: digest,
        state: "proposed",
        origin: "source-labels-v1",
        alias_group: null,
        version: 1,
        current_source: true,
      });
      return route.fulfill({
        status: 202,
        json: {
          id: rid,
          kind: "entity_annotation",
          status: "completed",
          trace_id: randomUUID(),
          error_code: null,
          result: null,
          paper_id: pid,
          reused_existing: false,
          model_calls: 0,
          engine: "source-labels-v1",
        },
      });
    }
    if (path.endsWith("/entity-mentions") && method === "GET")
      return route.fulfill({
        json: {
          items: state.mentions,
          total: state.mentions.length,
          limit: 50,
          offset: Number(url.searchParams.get("offset")),
        },
      });
    if (path.endsWith("/entity-mentions") && method === "POST") {
      const body = req.postDataJSON();
      const value = {
        id: randomUUID(),
        chunk_id: cid,
        name: Array.from(content)
          .slice(body.span_start, body.span_end)
          .join(""),
        entity_type: body.entity_type,
        span_start: body.span_start,
        span_end: body.span_end,
        content_sha256: digest,
        state: "proposed",
        origin: "manual-source-v1",
        alias_group: null,
        version: 1,
        current_source: true,
      };
      state.mentions.push(value);
      return route.fulfill({ status: 201, json: value });
    }
    if (path.includes("/entity-mentions/") && method === "PATCH") {
      const value = state.mentions.find((v) => path.endsWith(v.id)),
        body = req.postDataJSON();
      if (state.conflict)
        return route.fulfill({
          status: 409,
          json: { error_code: "entity_version_conflict" },
        });
      if (body.action === "correct") {
        value.name = Array.from(content)
          .slice(body.span_start, body.span_end)
          .join("");
        value.span_start = body.span_start;
        value.span_end = body.span_end;
        value.entity_type = body.entity_type;
        value.state = "proposed";
        state.linked = [];
      } else {
        value.state = body.action === "confirm" ? "confirmed" : "rejected";
        state.linked =
          body.action === "confirm"
            ? [
                {
                  entity_id: value.id,
                  name: value.name,
                  entity_type: value.entity_type,
                },
              ]
            : [];
      }
      value.version++;
      if (state.loseResponse) {
        state.loseResponse = false;
        return route.abort("failed");
      }
      return route.fulfill({ json: value });
    }
    if (path.endsWith("/entities"))
      return route.fulfill({ json: state.linked });
    if (path.includes("/entities/") && method === "DELETE") {
      state.linked = [];
      return route.fulfill({ json: { status: "removed" } });
    }
    if (path.endsWith("/annotation-review")) {
      state.completed = true;
      return route.fulfill({ json: { status: "completed" } });
    }
    return route.fulfill({ status: 404, json: { error_code: "not_found" } });
  });
  await page.goto("/#/knowledge");
  await page
    .getByText("MOCK review paper 实体标注：状态未读取", { exact: true })
    .click();
  const panel = page.getByLabel("实体提取与人工校正", { exact: true });
  await panel.locator(":scope > summary").click();
  await expect(
    panel.getByRole("button", { name: "读取当前片段与候选" }),
  ).toBeEnabled();
  return { state, panel, pid, cid, content, digest };
}

test("MOCK explicit local extraction, confirmation, rejection and complete review", async ({
  page,
}, info) => {
  const { state, panel } = await setup(page);
  expect(state.writes).toHaveLength(0);
  const start = panel.getByRole("button", { name: "生成或重试本地实体候选" });
  await expect(start).toBeDisabled();
  await panel.getByRole("checkbox", { name: "我会核对候选" }).check();
  await start.click();
  await panel.getByRole("button", { name: "读取当前片段与候选" }).click();
  await expect(panel).toContainText("数据集：MNIST · 待确认");
  await panel.getByRole("checkbox", { name: "我已核对整个片段" }).check();
  const complete = panel.getByRole("button", { name: "确认整个片段审阅完成" });
  await expect(complete).toBeDisabled();
  await panel.getByRole("button", { name: "确认 MNIST", exact: true }).click();
  await expect(panel).toContainText("数据集：MNIST · 已确认");
  await panel.getByRole("button", { name: "拒绝 MNIST", exact: true }).click();
  await expect(panel).toContainText("数据集：MNIST · 已拒绝");
  await panel.getByRole("checkbox", { name: "我已核对整个片段" }).check();
  await complete.click();
  await expect(
    page.getByText("MOCK review paper 实体标注：完成", { exact: true }),
  ).toBeVisible();
  expect(state.writes.map((w) => w.method)).toEqual([
    "POST",
    "PATCH",
    "PATCH",
    "POST",
  ]);
  expect(state.writes[0].body).toEqual({
    engine: "source-labels-v1",
    acknowledge_candidates_require_review: true,
  });
  await page.screenshot({
    path: info.outputPath("entity-review-complete.png"),
    fullPage: true,
  });
});

test("MOCK Unicode selection survives reload and correction remains proposed", async ({
  page,
}) => {
  const { state, panel, content, digest } = await setup(page);
  await panel.getByRole("button", { name: "读取当前片段与候选" }).click();
  const source = panel.getByLabel("用于实体核对的原文");
  await source.evaluate((el: HTMLTextAreaElement) => {
    const start = el.value.indexOf("科研数据集");
    el.focus();
    el.setSelectionRange(start, start + 5);
    el.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
  });
  await expect(panel.getByLabel("已选择实体原文")).toContainText("科研数据集");
  await panel.getByRole("button", { name: "保存选中原文为人工候选" }).click();
  await expect(panel).toContainText("数据集：科研数据集 · 待确认");
  const start = Array.from(
    content.slice(0, content.indexOf("科研数据集")),
  ).length;
  expect(state.writes[0].body).toEqual({
    entity_type: "dataset",
    span_start: start,
    span_end: start + 5,
    expected_content_sha256: digest,
  });
  await panel
    .getByRole("button", { name: "确认 科研数据集", exact: true })
    .click();
  await page.reload();
  await page
    .getByText("MOCK review paper 实体标注：状态未读取", { exact: true })
    .click();
  await panel.locator(":scope > summary").click();
  await panel.getByRole("button", { name: "读取当前片段与候选" }).click();
  await expect(panel).toContainText("数据集：科研数据集 · 已确认");
  await panel
    .getByRole("button", { name: "修改 科研数据集", exact: true })
    .click();
  await source.evaluate((el: HTMLTextAreaElement) => {
    const start = el.value.indexOf("NewMNIST");
    el.focus();
    el.setSelectionRange(start, start + 8);
    el.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
  });
  await panel.getByRole("button", { name: "保存实体修改" }).click();
  await expect(panel).toContainText("数据集：NewMNIST · 待确认");
  expect(state.mentions[0].version).toBe(3);
});

test("MOCK lost mutation response reads back once, conflict preserves source and version", async ({
  page,
}) => {
  const { state, panel } = await setup(page);
  await panel.getByRole("checkbox", { name: "我会核对候选" }).check();
  await panel.getByRole("button", { name: "生成或重试本地实体候选" }).click();
  await panel.getByRole("button", { name: "读取当前片段与候选" }).click();
  state.loseResponse = true;
  await panel.getByRole("button", { name: "确认 MNIST", exact: true }).click();
  await expect(panel).toContainText("数据集：MNIST · 已确认");
  await expect(panel.getByRole("alert")).toContainText("不自动重复写入");
  expect(state.writes.filter((w) => w.method === "PATCH")).toHaveLength(1);
  state.conflict = true;
  await panel.getByRole("button", { name: "拒绝 MNIST", exact: true }).click();
  await expect(panel.getByRole("alert")).toContainText(
    "核对当前状态、版本和原文",
  );
  expect(state.mentions[0].state).toBe("confirmed");
  expect(state.mentions[0].version).toBe(2);
});

test("MOCK nested links disclosure does not reload its parent and source failure disables writes", async ({
  page,
}) => {
  const { state, panel } = await setup(page);
  await panel.getByRole("button", { name: "读取当前片段与候选" }).click();
  await panel.getByText("核对和移除当前实体链接", { exact: true }).click();
  await expect(panel.getByLabel("用于实体核对的原文")).toBeVisible();
  expect(state.writes).toHaveLength(0);
  state.failedRead = true;
  await panel.getByRole("button", { name: "读取当前片段与候选" }).click();
  await expect(panel.getByRole("alert")).toContainText(
    "不能据此判断实体不存在",
  );
  await expect(
    panel.getByRole("button", { name: "生成或重试本地实体候选" }),
  ).toBeDisabled();
  await expect(panel.getByLabel("用于实体核对的原文")).toHaveCount(0);
});
