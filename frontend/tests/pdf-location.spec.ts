import { expect, test } from "@playwright/test";
import { completed, evidence, setupChat } from "./chat-fixtures";

// MOCK historical JSON: malformed optional location must not hide valid answer/source text.
for (const metadata of [
  {
    pdf_regions: [{ source_id: "old", page_no: 7, bbox: { left: "invalid" } }],
    pdf_location: "available",
  },
  { pdf_regions: null, pdf_location: "unknown", page_location: "invalid" },
]) {
  test(`MOCK optional PDF geometry degrades while original evidence remains readable ${JSON.stringify(metadata)}`, async ({
    page,
  }) => {
    await setupChat(page, {
      result: {
        ...completed,
        result: {
          ...completed.result,
          reranked_evidence: [{ ...evidence, ...metadata }],
        },
      },
    });
    await page.goto("/#/rag");
    await page.getByLabel("研究问题").fill("MOCK original source");
    await page.getByRole("button", { name: "发送", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "已通过自动证据校验" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "文献 · p.7" }).click();
    await expect(page.getByRole("dialog", { name: "引用原文" })).toContainText(
      evidence.quote,
    );
  });
}
