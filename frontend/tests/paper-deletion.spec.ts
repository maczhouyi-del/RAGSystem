import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { completed, evidence, setupChat } from "./chat-fixtures";

// MOCK HTTP persistence. TASK-06 real PG/RQ tests prove retrieval exclusion,
// rollback, worker races and data isolation; this file proves UI contracts only.
const paperId = "00000000-0000-4000-8000-000000000071";
const otherId = "00000000-0000-4000-8000-000000000072";
const cleanupId = "00000000-0000-4000-8000-000000000073";
const copies = [
  "desktop_documents_cache",
  "external_pdf_reader",
  "downloaded_exports",
  "user_saved_files",
  "backups_and_sync",
  "external_provider_retention",
  "conversation_answer_prose",
];
const targetSource = {
  ...evidence,
  paper: { paper_id: paperId, title: "MOCK target paper" },
};
const otherSource = {
  ...evidence,
  evidence_id: "00000000-0000-4000-8000-000000000074",
  paper: { paper_id: otherId, title: "MOCK other paper" },
  page_start: 3,
  page_end: 3,
  quote: "MOCK preserved other source.",
};

async function setup(page: Page) {
  const chat = await setupChat(page);
  const conversation = chat.create("MOCK preserved conversation");
  const detailed = {
    ...completed,
    result: {
      answer: `MOCK historical prose. [E:${targetSource.evidence_id}] Other fact. [E:${otherSource.evidence_id}]`,
      reranked_evidence: [targetSource, otherSource],
    },
  };
  const message = chat.makeMessage(
    conversation,
    "assistant",
    detailed.result.answer,
    detailed,
  );
  const paper = {
    id: paperId,
    title: "MOCK target paper",
    authors: ["Alice"],
    year: 2024,
    venue: null,
    status: "indexed",
    error_code: null,
    chunk_count: 2,
    metadata_version: 1,
  };
  const other = { ...paper, id: otherId, title: "MOCK other paper" };
  const state = {
    paper,
    removed: false,
    previewFailure: false,
    lostResponse: false,
    deletionFailure: false,
    statusFailure: false,
    ledger: null as null | {
      paper_id: string;
      library_removed: true;
      cleanup_run_id: string;
      cleanup_status: string;
      error_code: string | null;
      retained_copies: string[];
      retained_managed_files: string[];
    },
    deletes: [] as Record<string, unknown>[],
    retries: 0,
    previews: 0,
    statusReads: 0,
  };
  function retireHistory() {
    const unavailable = {
      source_availability: "unavailable",
      source_unavailable_reason: "source_deleted",
    };
    message.updated_at = "2026-10-09T00:00:00Z";
    message.metadata = {
      ...unavailable,
      presentation: {
        ...unavailable,
        limitations: [],
        citation_refs: [
          {
            ...unavailable,
            evidence_id: targetSource.evidence_id,
            page_start: 7,
            page_end: 8,
          },
          { evidence_id: otherSource.evidence_id, page_start: 3, page_end: 3 },
        ],
      },
    };
    chat.runs.set(detailed.id, {
      ...detailed,
      result: {
        ...detailed.result,
        ...unavailable,
        reranked_evidence: [
          {
            ...targetSource,
            ...unavailable,
            quote: "",
            content: "",
            paper: { ...targetSource.paper, ...unavailable },
          },
          otherSource,
        ],
      },
    });
  }
  await page.route("**/api/papers/search?*", (route) => {
    const items = state.removed ? [other] : [state.paper, other];
    return route.fulfill({
      json: { items, total: items.length, limit: 50, offset: 0 },
    });
  });
  await page.route(`**/api/papers/${paperId}`, (route) => {
    if (route.request().method() === "GET")
      return route.fulfill({
        status: state.removed ? 410 : 200,
        json: state.removed ? { error_code: "source_deleted" } : state.paper,
      });
    const body = route.request().postDataJSON();
    state.deletes.push(body);
    if (body.expected_metadata_version !== state.paper.metadata_version)
      return route.fulfill({
        status: 409,
        json: { error_code: "paper_metadata_conflict" },
      });
    if (state.deletionFailure)
      return route.fulfill({
        status: 503,
        json: { error_code: "infrastructure_unavailable" },
      });
    state.removed = true;
    state.ledger = {
      paper_id: paperId,
      library_removed: true,
      cleanup_run_id: cleanupId,
      cleanup_status: "queued",
      error_code: null,
      retained_copies: copies,
      retained_managed_files: [],
    };
    retireHistory();
    if (state.lostResponse) return route.abort("failed");
    return route.fulfill({ status: 202, json: state.ledger });
  });
  await page.route(`**/api/papers/${paperId}/deletion-preview`, (route) => {
    state.previews += 1;
    return route.fulfill({
      status: state.previewFailure ? 503 : 200,
      json: state.previewFailure
        ? { error_code: "infrastructure_unavailable" }
        : {
            paper_id: paperId,
            metadata_version: state.paper.metadata_version,
            chunks: 2,
            evidence: 1,
            pending_imports: 1,
            scope: "current_library",
            retained_copies: copies,
          },
    });
  });
  await page.route(`**/api/papers/${paperId}/deletion`, (route) => {
    state.statusReads += 1;
    if (state.statusFailure)
      return route.fulfill({
        status: 503,
        json: { error_code: "infrastructure_unavailable" },
      });
    return route.fulfill({
      status: state.ledger ? 200 : 404,
      json: state.ledger ?? { error_code: "paper_deletion_not_found" },
    });
  });
  await page.route(`**/api/papers/${paperId}/deletion/retry`, (route) => {
    state.retries += 1;
    expect(route.request().method()).toBe("POST");
    expect(route.request().postDataJSON()).toEqual({});
    state.ledger = {
      ...state.ledger!,
      cleanup_run_id: "00000000-0000-4000-8000-000000000075",
      cleanup_status: "queued",
      error_code: null,
    };
    return route.fulfill({ status: 202, json: state.ledger });
  });
  await page.goto("/#/knowledge");
  await expect(page.locator("tbody tr")).toHaveCount(2);
  return { state, chat, conversation, message, retireHistory, detailed };
}
async function confirm(page: Page) {
  await page
    .getByRole("button", { name: "删除 MOCK target paper", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "确认删除文献" });
  await dialog.getByRole("checkbox").check();
  await dialog
    .getByRole("button", { name: "确认移出知识库", exact: true })
    .click();
  return dialog;
}
const status = (page: Page) =>
  page.getByRole("region", { name: `删除状态 ${paperId}`, exact: true });

test("deletion requires preview and explicit acknowledgement; cancel and Escape write nothing", async ({
  page,
}) => {
  const { state } = await setup(page);
  await page
    .getByRole("button", { name: "删除 MOCK target paper", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "确认删除文献" });
  await expect(dialog).toContainText(
    "2 个文本块、1 条证据、1 个未完成来源处理任务（含导入与实体提取）",
  );
  await expect(dialog).toContainText("备份与同步副本");
  await expect(dialog).toContainText("历史回答、问题和摘要正文");
  await expect(
    dialog.getByRole("button", { name: "确认移出知识库" }),
  ).toBeDisabled();
  await expect(
    dialog.getByRole("button", { name: "取消删除" }),
  ).toBeInViewport();
  await expect(
    dialog.getByRole("button", { name: "确认移出知识库" }),
  ).toBeInViewport();
  await page.screenshot({
    path: test.info().outputPath("paper-deletion-confirmation.png"),
    fullPage: true,
  });
  await dialog.getByRole("checkbox").check();
  await dialog.getByRole("button", { name: "取消删除" }).click();
  await expect(dialog).toHaveCount(0);
  await page
    .getByRole("button", { name: "删除 MOCK target paper", exact: true })
    .click();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  expect(state.deletes).toEqual([]);
  expect(state.removed).toBe(false);
  expect(state.retries).toBe(0);
  await expect(page.locator("tbody tr")).toHaveCount(2);
});

test("confirmed deletion refreshes the library; cleanup progress survives reload without mutation replay", async ({
  page,
}) => {
  const { state, chat, message } = await setup(page);
  const prose = message.content;
  await confirm(page);
  await expect(status(page)).toContainText("已移出当前知识库");
  await expect(status(page)).toContainText("等待清理");
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await expect(
    page.getByRole("link", { name: "MOCK other paper", exact: true }),
  ).toBeVisible();
  expect(state.deletes).toEqual([
    {
      confirm_paper_id: paperId,
      expected_metadata_version: 1,
      scope: "current_library",
      acknowledge_retained_copies: true,
    },
  ]);
  expect(chat.conversations.size).toBe(1);
  expect(message.content).toBe(prose);
  await page.reload();
  await expect(status(page)).toContainText("等待清理");
  expect(state.deletes).toHaveLength(1);
  expect(state.retries).toBe(0);
  expect(
    await page.evaluate(() =>
      JSON.parse(
        localStorage.getItem("ragagent-paper-deletion-status-ids-v1")!,
      ),
    ),
  ).toEqual([paperId]);
  state.ledger!.cleanup_status = "completed";
  await status(page).getByRole("button", { name: "读取最新删除状态" }).click();
  await expect(status(page)).toContainText("受管文件清理完成");
  await page.screenshot({
    path: test.info().outputPath("paper-deletion-completed.png"),
    fullPage: true,
  });
});

test("preview failure is read-only and can recover before confirmation", async ({
  page,
}) => {
  const { state } = await setup(page);
  state.previewFailure = true;
  await page
    .getByRole("button", { name: "删除 MOCK target paper", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "确认删除文献" });
  await expect(dialog.getByRole("alert")).toContainText("HTTP 503");
  await expect(
    dialog.getByRole("button", { name: "确认移出知识库" }),
  ).toBeDisabled();
  expect(state.deletes).toHaveLength(0);
  state.previewFailure = false;
  await dialog.getByRole("button", { name: "重新读取删除预览" }).click();
  await expect(dialog.getByRole("checkbox")).toBeVisible();
  await dialog.getByRole("button", { name: "取消删除" }).click();
  expect(state.removed).toBe(false);
});

test("concurrent metadata change requires fresh preview and a new acknowledgement", async ({
  page,
}) => {
  const { state } = await setup(page);
  await page
    .getByRole("button", { name: "删除 MOCK target paper", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "确认删除文献" });
  await dialog.getByRole("checkbox").check();
  state.paper = {
    ...state.paper,
    title: "MOCK changed target",
    metadata_version: 2,
  };
  await dialog.getByRole("button", { name: "确认移出知识库" }).click();
  await expect(dialog.getByRole("alert")).toContainText("本次未删除");
  await expect(
    dialog.getByRole("button", { name: "确认移出知识库" }),
  ).toBeDisabled();
  expect(state.removed).toBe(false);
  await dialog.getByRole("button", { name: "重新读取删除预览" }).click();
  await expect(dialog).toContainText("MOCK changed target");
  await expect(dialog.getByRole("checkbox")).not.toBeChecked();
  await dialog.getByRole("checkbox").check();
  await dialog.getByRole("button", { name: "确认移出知识库" }).click();
  await expect(status(page)).toContainText("已移出当前知识库");
  expect(state.deletes.map((value) => value.expected_metadata_version)).toEqual(
    [1, 2],
  );
});

test("lost deletion response reads the ledger and never blindly resends DELETE", async ({
  page,
}) => {
  const { state } = await setup(page);
  state.lostResponse = true;
  await confirm(page);
  await expect(status(page)).toContainText("已移出当前知识库");
  await expect(page.locator("tbody tr")).toHaveCount(1);
  expect(state.deletes).toHaveLength(1);
  expect(state.statusReads).toBeGreaterThan(0);
  expect(state.retries).toBe(0);
});

test("uncommitted deletion failure keeps documents and offers only read-only reconciliation", async ({
  page,
}) => {
  const { state } = await setup(page);
  state.deletionFailure = true;
  await confirm(page);
  await expect(status(page)).toContainText("删除结果待核对");
  await expect(status(page).getByRole("alert")).toContainText(
    "paper_deletion_not_found",
  );
  await expect(status(page).getByRole("alert")).toContainText(
    "数据库或 Redis 不可用",
  );
  await expect(page.locator("tbody tr")).toHaveCount(2);
  await expect(
    status(page).getByRole("button", { name: "重试清理文件与队列" }),
  ).toHaveCount(0);
  await status(page).getByRole("button", { name: "读取最新删除状态" }).click();
  expect(state.deletes).toHaveLength(1);
  expect(state.retries).toBe(0);
});

test("failed cleanup keeps removal effective and explicit retry follows the new server Run", async ({
  page,
}) => {
  const { state } = await setup(page);
  await confirm(page);
  await expect(status(page)).toContainText("等待清理");
  state.ledger!.cleanup_status = "failed";
  state.ledger!.error_code = "cleanup_file_changed";
  state.ledger!.retained_managed_files = ["shared_by_other_paper"];
  await status(page).getByRole("button", { name: "读取最新删除状态" }).click();
  await expect(status(page).getByRole("alert")).toContainText(
    "不要强行修改摘要",
  );
  await expect(status(page)).toContainText("其他论文仍在使用");
  await status(page)
    .getByRole("button", { name: "重试清理文件与队列" })
    .click();
  await expect(status(page)).toContainText(
    "00000000-0000-4000-8000-000000000075",
  );
  expect(state.retries).toBe(1);
  expect(state.deletes).toHaveLength(1);
  await expect(page.locator("tbody tr")).toHaveCount(1);
});

test("historical answer flags deleted citations while other sources and conversation remain usable", async ({
  page,
}) => {
  const { chat, conversation, message } = await setup(page);
  const prose = message.content;
  await confirm(page);
  await expect(status(page)).toContainText("已移出当前知识库");
  await page.getByRole("button", { name: "RAG", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "历史回答 · 来源不可用，当前不可验证" }),
  ).toBeVisible();
  await expect(page.locator(".report")).toContainText("MOCK historical prose.");
  await expect(page.locator(".report .source-unavailable")).toContainText(
    "来源已删除",
  );
  await expect(
    page.getByRole("button", { name: "文献 · p.7", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "文献 · p.3", exact: true }).click();
  await expect(page.getByLabel("主引用原文", { exact: true })).toHaveText(
    otherSource.quote,
  );
  await expect(
    page.getByRole("link", { name: "打开原始 PDF" }),
  ).toHaveAttribute("href", `/api/papers/${otherId}/pdf#page=3`);
  expect(chat.conversations.get(conversation.id)?.title).toBe(
    "MOCK preserved conversation",
  );
  expect(message.status).toBe("completed");
  expect(message.content).toBe(prose);
});

test("a previously cached citation rechecks the Run after deletion in another window", async ({
  page,
}) => {
  const { conversation, retireHistory } = await setup(page);
  await page.goto(`/#/rag/${conversation.id}`);
  await page.getByRole("button", { name: "文献 · p.7", exact: true }).click();
  await expect(page.getByLabel("主引用原文", { exact: true })).toHaveText(
    targetSource.quote,
  );
  await page.getByRole("button", { name: "关闭", exact: true }).click();
  retireHistory();
  await page.getByRole("button", { name: "文献 · p.7", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "引用原文" })).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "历史回答 · 来源不可用，当前不可验证" }),
  ).toBeVisible();
  await expect(page.locator(".report .source-unavailable")).toContainText(
    "来源已删除",
  );
  await page.getByRole("button", { name: "文献 · p.3", exact: true }).click();
  await expect(page.getByLabel("主引用原文", { exact: true })).toHaveText(
    otherSource.quote,
  );
});

test("source revision reconciliation aborts late old Run detail and closes the old quote", async ({
  page,
}) => {
  const { conversation, retireHistory, detailed } = await setup(page);
  await page.goto(`/#/rag/${conversation.id}`);
  let release!: () => void;
  const barrier = new Promise<void>((resolve) => {
    release = resolve;
  });
  let requested!: () => void;
  const started = new Promise<void>((resolve) => {
    requested = resolve;
  });
  await page.route(`**/api/runs/${detailed.id}`, async (route) => {
    requested();
    await barrier;
    try {
      await route.fulfill({ json: detailed });
    } catch {
      /* Client aborted obsolete detail. */
    }
  });
  await page.getByRole("button", { name: "文献 · p.7", exact: true }).click();
  await started;
  const aborted = page.waitForEvent("requestfailed", {
    predicate: (request) => request.url().endsWith(`/api/runs/${detailed.id}`),
  });
  retireHistory();
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(
    page.getByRole("heading", { name: "历史回答 · 来源不可用，当前不可验证" }),
  ).toBeVisible();
  await aborted;
  release();
  await expect(page.getByRole("dialog", { name: "引用原文" })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "文献 · p.7", exact: true }),
  ).toHaveCount(0);
  await expect(page.locator(".report .source-unavailable")).toBeVisible();
});

test("legacy source-unavailable message without presentation never claims current verification", async ({
  page,
}) => {
  const { conversation, message, retireHistory } = await setup(page);
  retireHistory();
  message.metadata = {
    source_availability: "unavailable",
    source_unavailable_reason: "source_deleted",
  };
  await page.goto(`/#/rag/${conversation.id}`);
  await expect(
    page.getByRole("heading", { name: "历史回答 · 来源不可用，当前不可验证" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "已通过自动证据校验" }),
  ).toHaveCount(0);
  await expect(page.locator(".report .source-unavailable")).toBeVisible();
});

test("pending deletion cannot be submitted twice or dismissed as an undo", async ({
  page,
}) => {
  const { state } = await setup(page);
  let release!: () => void;
  const barrier = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(`**/api/papers/${paperId}`, async (route) => {
    if (route.request().method() === "DELETE") await barrier;
    await route.fallback();
  });
  await confirm(page);
  const dialog = page.getByRole("dialog", { name: "确认删除文献" });
  await expect(
    dialog.getByRole("button", { name: "正在提交删除，请勿重复操作…" }),
  ).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "取消删除" })).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();
  release();
  await expect(status(page)).toContainText("已移出当前知识库");
  expect(state.deletes).toHaveLength(1);
});

test("status service outage preserves the already confirmed library removal", async ({
  page,
}) => {
  const { state } = await setup(page);
  await confirm(page);
  await expect(status(page)).toContainText("已移出当前知识库");
  state.statusFailure = true;
  await status(page).getByRole("button", { name: "读取最新删除状态" }).click();
  await expect(status(page).getByRole("alert")).toContainText(
    "数据库或 Redis 不可用",
  );
  await expect(status(page)).toContainText("已移出当前知识库");
  await expect(page.locator("tbody tr")).toHaveCount(1);
  state.statusFailure = false;
  state.ledger!.cleanup_status = "completed";
  await status(page).getByRole("button", { name: "读取最新删除状态" }).click();
  await expect(status(page)).toContainText("受管文件清理完成");
  expect(state.deletes).toHaveLength(1);
});

test("a late older message page cannot overwrite reconciled source-unavailable metadata", async ({
  page,
}) => {
  const { conversation, message, retireHistory } = await setup(page);
  const oldMessage = JSON.parse(JSON.stringify(message));
  let release!: () => void;
  const barrier = new Promise<void>((resolve) => {
    release = resolve;
  });
  let requested!: () => void;
  const started = new Promise<void>((resolve) => {
    requested = resolve;
  });
  let calls = 0;
  await page.route(
    `**/api/conversations/${conversation.id}/messages?limit=50`,
    async (route) => {
      calls += 1;
      if (calls === 1) {
        requested();
        await barrier;
        const { result: _detail, ...runSummary } = oldMessage.run;
        await route.fulfill({ json: [{ ...oldMessage, run: runSummary }] });
      } else await route.fallback();
    },
  );
  await page.goto(`/#/rag/${conversation.id}`);
  await started;
  retireHistory();
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(
    page.getByRole("heading", { name: "历史回答 · 来源不可用，当前不可验证" }),
  ).toBeVisible();
  await expect(page.getByLabel("聊天消息", { exact: true })).toHaveAttribute(
    "aria-busy",
    "true",
  );
  release();
  await expect(page.getByLabel("聊天消息", { exact: true })).toHaveAttribute(
    "aria-busy",
    "false",
  );
  await expect(
    page.getByRole("heading", { name: "历史回答 · 来源不可用，当前不可验证" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "文献 · p.7", exact: true }),
  ).toHaveCount(0);
});
