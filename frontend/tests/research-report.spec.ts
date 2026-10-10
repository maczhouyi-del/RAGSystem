import { expect, test } from "@playwright/test";
import demo from "../../tests/fixtures/report-demo.json" with { type: "json" };
import { completed, setupChat } from "./chat-fixtures";

// DEMO ONLY / NOT A BENCHMARK / NOT MANUALLY ANNOTATED.
// The Python test checks that this fixture is actual deterministic synthesis output.
test("MOCK structured report renders all sections, incomparable experiments and source links", async ({
  page,
}) => {
  const chat = await setupChat(page);
  const conversation = chat.create("DEMO report", "research");
  const quotes = [
    "Alpha uses contrastive training on DemoSet; accuracy 91.5 %; test split; single GPU. Participant demographics are not reported. Improvement observed.",
    "Beta uses baseline training on DemoSet; accuracy 0.89 fraction; validation split; CPU. No improvement observed.",
  ];
  const sources = quotes.map((quote, i) => ({
    evidence_id: demo.evidence_ids[i],
    paper: {
      paper_id: demo.paper_ids[i],
      title: i ? "DEMO Beta" : "DEMO Alpha",
    },
    chunk_id: `chunk-${i}`,
    section_id: "s1",
    section_path: "Methods",
    page_start: 2,
    page_end: 2,
    quote,
    content: quote,
    span_start: 0,
    span_end: quote.length,
  }));
  chat.makeMessage(conversation, "assistant", demo.markdown, {
    ...completed,
    kind: "research",
    result: {
      draft_report: demo.markdown,
      structured_report: demo,
      evidence_pool: sources,
      review_result: {
        decision: "PASS",
        validation: { valid: true, report_bindings_verified: true },
      },
    },
  });
  await page.goto(`/#/research/${conversation.id}`);
  for (const section of demo.sections)
    await expect(
      page.getByRole("heading", { name: section.title, exact: true }),
    ).toBeVisible();
  const table = page.getByRole("table");
  await expect(table).toBeVisible();
  const alpha = table.getByRole("row").filter({ hasText: "DEMO Alpha" });
  const beta = table.getByRole("row").filter({ hasText: "DEMO Beta" });
  await expect(alpha).toContainText("91.5");
  await expect(alpha).toContainText("test split");
  await expect(alpha).toContainText("single GPU");
  await expect(alpha).toContainText("原文明确未报告");
  await expect(beta).toContainText("0.89");
  await expect(beta).toContainText("fraction");
  await expect(beta).toContainText("validation split");
  await expect(beta).toContainText("CPU");
  await expect(beta).toContainText("不代表原文未报告");
  await expect(
    page.getByText("单位：原文字段不同", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByText("数据划分：原文字段不同", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByText("No improvement observed.", { exact: false }),
  ).toBeVisible();
  await beta.getByRole("button", { name: "文献 · p.2" }).first().click();
  const dialog = page.getByRole("dialog", { name: "引用原文" });
  await expect(dialog.getByLabel("主引用原文", { exact: true })).toHaveText(
    quotes[1],
  );
  await expect(
    dialog.getByRole("link", { name: "打开原始 PDF", exact: true }),
  ).toHaveAttribute("href", "/api/papers/paper-1/pdf#page=2");
  await dialog.getByRole("button", { name: "关闭", exact: true }).click();
  await page.screenshot({
    path: test.info().outputPath("research-report.png"),
    fullPage: true,
  });
});

test("MOCK unfinished research never publishes report facts as a verified answer", async ({
  page,
}) => {
  const chat = await setupChat(page);
  const conversation = chat.create("DEMO reviewing", "research");
  chat.makeMessage(conversation, "assistant", "", {
    ...completed,
    kind: "research",
    status: "running",
    result: {
      draft_report: demo.markdown,
      review_result: { decision: "NEED_REVISION" },
    },
  });
  await page.goto(`/#/research/${conversation.id}`);
  await expect(
    page.getByRole("heading", { name: "执行中", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "结果对比", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByRole("table")).toHaveCount(0);
});
