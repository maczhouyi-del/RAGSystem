import { expect, test, type Page } from "@playwright/test";
import { completed, evidence, setupChat } from "./chat-fixtures";

// MOCK HTTP/IPC contracts, never a scientific benchmark or native system-reader test.
const paperId = "00000000-0000-0000-0000-000000000011";
async function show(
  page: Page,
  sources: object[],
  options: Record<string, unknown> = {},
  mode: "rag" | "research" = "rag",
) {
  const chat = await setupChat(page);
  const conversation = chat.create("MOCK PDF reading", mode);
  const answer = sources
    .map((source) => `[E:${(source as typeof evidence).evidence_id}]`)
    .join(" ");
  const detailed = {
    ...completed,
    kind: mode,
    result: { answer, reranked_evidence: sources, ...options },
  };
  chat.makeMessage(conversation, "assistant", answer, detailed);
  await page.goto(`/#/${mode}/${conversation.id}`);
  return chat;
}
function region(page: number, bbox: object | null = null) {
  return {
    source_id: "#/tables/0",
    page_no: page,
    bbox,
    parser_charspan: null,
    source_start: null,
    source_end: null,
    scope: "element",
    status: bbox ? "available" : "unavailable",
    text_mapping: "unavailable",
    unavailable_reason: bbox ? null : "not_provided",
  };
}
const bbox = {
  left: 10,
  top: 20,
  right: 100,
  bottom: 40,
  page_width: 612,
  page_height: 792,
  coord_origin: "TOPLEFT",
  units: "page_units",
};

test("MOCK distinct citations open their own paper and original quote", async ({
  page,
}) => {
  const second = {
    ...evidence,
    evidence_id: "00000000-0000-0000-0000-000000000002",
    paper: { paper_id: paperId, title: "MOCK second paper" },
    page_start: 9,
    page_end: 9,
    quote: "Second original quote.",
  };
  const chat = await show(page, [evidence, second]);
  await page.getByRole("button", { name: "文献 · p.7" }).click();
  const dialog = page.getByRole("dialog", { name: "引用原文" });
  await expect(dialog.getByLabel("主引用原文", { exact: true })).toHaveText(
    evidence.quote,
  );
  await expect(
    dialog.getByRole("link", { name: "打开原始 PDF", exact: true }),
  ).toHaveAttribute("href", "/api/papers/paper-1/pdf#page=7");
  await dialog.getByRole("button", { name: "关闭", exact: true }).click();
  await page.getByRole("button", { name: "文献 · p.9" }).click();
  await expect(
    dialog.getByRole("heading", { name: "MOCK second paper" }),
  ).toBeVisible();
  await expect(dialog.getByLabel("主引用原文", { exact: true })).toHaveText(
    second.quote,
  );
  await expect(
    dialog.getByRole("link", { name: "打开原始 PDF", exact: true }),
  ).toHaveAttribute("href", `/api/papers/${paperId}/pdf#page=9`);
  expect(chat.fullRunRequests).toHaveLength(2);
});

test("MOCK multi-page table exposes actual region pages and independent caption source", async ({
  page,
}) => {
  const table = {
    ...evidence,
    page_end: 9,
    quote: "| Method | score (%) |\n| --- | --- |\n| Alpha | 91.5 |\n",
    paper: {
      paper_id: paperId,
      title: "MOCK table paper",
      pdf_sha256: "a".repeat(64),
    },
    pdf_regions: [region(7, bbox), region(9)],
    pdf_location: "available",
    source_context: [
      {
        source_id: "#/caption/0",
        element_type: "caption",
        section_path: ["Results"],
        page_start: 6,
        page_end: 6,
        content: "Table caption (%)",
        quote: "Table caption (%)",
        span_start: 0,
        span_end: 17,
      },
    ],
  };
  await show(page, [table]);
  await page.getByRole("button", { name: "文献 · p.7" }).click();
  const dialog = page.getByRole("dialog", { name: "引用原文" });
  await expect(
    dialog.getByRole("link", { name: "打开候选页 7", exact: true }),
  ).toHaveAttribute("href", `/api/papers/${paperId}/pdf#page=7`);
  await expect(
    dialog.getByRole("link", { name: "打开候选页 9", exact: true }),
  ).toBeVisible();
  await expect(
    dialog.getByRole("link", { name: "打开候选页 8", exact: true }),
  ).toHaveCount(0);
  await expect(dialog.getByLabel("辅助原文", { exact: true })).toContainText(
    "Table caption (%)",
  );
  await expect(
    dialog.getByRole("link", { name: "打开辅助片段所在 PDF 页" }),
  ).toHaveAttribute("href", `/api/papers/${paperId}/pdf#page=6`);
  await expect(dialog).toContainText("部分来源区域不可用");
  await expect(dialog).toContainText("不表示逐字结论高亮");
  await expect(dialog.locator("mark")).toHaveCount(0);
  await page.screenshot({
    path: test.info().outputPath("pdf-reading-table.png"),
  });
});

test("MOCK missing page and forged geometry fall back to original PDF without page 1", async ({
  page,
}) => {
  await show(page, [
    {
      ...evidence,
      page_start: 1,
      page_end: 1,
      page_location: "unavailable",
      pdf_location: "available",
      pdf_regions: [region(1, { ...bbox, right: 9999 })],
    },
  ]);
  await expect(
    page.getByRole("button", { name: "文献 · 页码未知" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "文献 · p.1", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "文献 · 页码未知" }).click();
  const dialog = page.getByRole("dialog", { name: "引用原文" });
  await expect(
    dialog.getByRole("link", { name: "打开原始 PDF", exact: true }),
  ).toHaveAttribute("href", "/api/papers/paper-1/pdf");
  await expect(dialog).toContainText("目标页未知");
  await expect(dialog.getByLabel("主引用原文", { exact: true })).toHaveText(
    evidence.quote,
  );
  await expect(dialog.locator("mark")).toHaveCount(0);
});

const content = "前言😀方法达到23%。结尾";
const quoted = Array.from(content).slice(2, 11).join("");
const original = {
  ...evidence,
  paper: { paper_id: paperId, title: "MOCK Unicode paper" },
  content,
  quote: quoted,
  span_start: 2,
  span_end: 11,
};
const pair = {
  claim_id: "metric",
  evidence_id: evidence.evidence_id,
  supporting_span_start: 3,
  supporting_span_end: 11,
};
for (const mode of ["rag", "research"]) {
  test(`MOCK ${mode} reviewed Unicode span marks only matching original quote`, async ({
    page,
  }) => {
    const validation = { valid: true, supported_pairs: [pair] };
    await show(
      page,
      [original],
      mode === "rag"
        ? { citation_validation: validation }
        : { review_result: { decision: "PASS", validation } },
      mode as "rag" | "research",
    );
    await page.getByRole("button", { name: "文献 · p.7" }).click();
    await expect(page.getByLabel("主引用原文", { exact: true })).toHaveText(
      quoted,
    );
    await expect(
      page.getByLabel("主引用原文", { exact: true }).locator("mark"),
    ).toHaveText("方法达到23%。");
  });
}
for (const defect of ["outside-span", "quote-mismatch", "unverified"]) {
  test(`MOCK ${defect} never marks a false support span`, async ({ page }) => {
    const source =
      defect === "quote-mismatch"
        ? { ...original, quote: "Different source quote." }
        : original;
    await show(page, [source], {
      citation_validation: {
        valid: defect !== "unverified",
        supported_pairs: [
          defect === "outside-span"
            ? { ...pair, supporting_span_end: 999 }
            : pair,
        ],
      },
    });
    await page.getByRole("button", { name: "文献 · p.7" }).click();
    await expect(page.getByLabel("主引用原文", { exact: true })).toHaveText(
      source.quote,
    );
    await expect(page.getByRole("dialog").locator("mark")).toHaveCount(0);
  });
}
for (const unknown of [false, true]) {
  test(`MOCK Desktop citation calls restricted IPC opener with ${unknown ? "unknown" : "known"} page`, async ({
    page,
  }) => {
    const source = {
      ...evidence,
      paper: { paper_id: paperId, title: "MOCK Desktop source" },
      page_location: unknown ? "unavailable" : "available",
    };
    await show(page, [source]);
    await page
      .getByRole("button", { name: unknown ? "文献 · 页码未知" : "文献 · p.7" })
      .click();
    await page.evaluate(() => {
      const win = window as unknown as {
        isTauri: boolean;
        __TAURI_INTERNALS__: object;
        openerCalls: unknown[];
      };
      win.isTauri = true;
      win.openerCalls = [];
      win.__TAURI_INTERNALS__ = {
        invoke: async (command: string, args: unknown) => {
          win.openerCalls.push({ command, args });
        },
      };
    });
    await page.getByRole("link", { name: "打开原始 PDF", exact: true }).click();
    await expect
      .poll(() =>
        page.evaluate(
          () => (window as unknown as { openerCalls: unknown[] }).openerCalls,
        ),
      )
      .toEqual([
        {
          command: "open_resource",
          args: {
            path: `/api/papers/${paperId}/pdf${unknown ? "" : "#page=7"}`,
          },
        },
      ]);
    expect(page.context().pages()).toHaveLength(1);
  });
}
