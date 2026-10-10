import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import fixture from "../../tests/fixtures/report-exports.json" with { type: "json" };
import { completed, setupChat } from "./chat-fixtures";

// MOCK HTTP, actual browser file downloads, DEMO ONLY / NOT A BENCHMARK.
async function show(page: Page, legacy = false) {
  const chat = await setupChat(page);
  const conversation = chat.create("DEMO export", "research");
  chat.makeMessage(conversation, "assistant", fixture.result.draft_report, {
    ...completed,
    id: fixture.run_id,
    kind: "research",
    result: legacy ? null : fixture.result,
  });
  await page.goto(`/#/research/${conversation.id}`);
  return chat;
}
const formats = [
  ["report.md", "Markdown 报告"],
  ["comparison.csv", "比较表 CSV"],
  ["references.bib", "BibTeX 参考文献"],
  ["citations.json", "引用清单 JSON"],
] as const;

for (const [name, label] of formats) {
  test(`MOCK Web ${label} downloads exact persisted bytes with a safe filename`, async ({
    page,
  }) => {
    const chat = await show(page);
    await page.route(
      `**/api/runs/${fixture.run_id}/exports/${name}`,
      async (route) => {
        await route.fulfill({
          body: Buffer.from(fixture.artifacts[name], "utf8"),
          headers: {
            "content-type": "application/octet-stream",
            "content-disposition": 'attachment; filename="../../untrusted.exe"',
          },
        });
      },
    );
    await page.getByLabel("导出格式").selectOption(name);
    const downloading = page.waitForEvent("download");
    await page
      .getByRole("button", { name: "导出当前结果", exact: true })
      .click();
    const download = await downloading;
    expect(download.suggestedFilename()).toBe(
      `ragagent-${fixture.run_id}-${name}`,
    );
    const path = await download.path();
    expect(path).not.toBeNull();
    expect(await readFile(path!)).toEqual(
      Buffer.from(fixture.artifacts[name], "utf8"),
    );
    expect(chat.fullRunRequests).toHaveLength(0);
    await expect(
      page.getByText("浏览器下载已发起：", { exact: false }),
    ).toBeVisible();
  });
}

test("MOCK legacy visible report remains downloadable without a structured Run result", async ({
  page,
}) => {
  await show(page, true);
  await page.route(`**/api/runs/${fixture.run_id}/exports/report.md`, (route) =>
    route.fulfill({ body: fixture.artifacts["report.md"] }),
  );
  const downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出当前结果", exact: true }).click();
  expect((await downloading).suggestedFilename()).toContain("report.md");
});

test("MOCK failed Web export does not download a raw error and can be retried", async ({
  page,
}) => {
  await show(page);
  let fail = true;
  let downloads = 0;
  page.on("download", () => downloads++);
  await page.route(`**/api/runs/${fixture.run_id}/exports/report.md`, (route) =>
    route.fulfill(
      fail
        ? {
            status: 409,
            contentType: "application/json",
            json: {
              error_code: "report_not_released",
              private: "PRIVATE_NOT_SHOWN",
            },
          }
        : { body: fixture.artifacts["report.md"] },
    ),
  );
  await page.getByRole("button", { name: "导出当前结果", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("尚未发布最终结果");
  await expect(page.getByText("PRIVATE_NOT_SHOWN")).toHaveCount(0);
  expect(downloads).toBe(0);
  fail = false;
  const downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出当前结果", exact: true }).click();
  await downloading;
});

test("MOCK Desktop export uses the fixed native saver and reports Downloads receipt", async ({
  page,
}) => {
  await show(page);
  await page.evaluate(() => {
    const win = window as unknown as {
      __TAURI_INTERNALS__: object;
      exports: object[];
    };
    win.exports = [];
    Object.assign(globalThis, { isTauri: true });
    win.__TAURI_INTERNALS__ = {
      invoke: async (command: string, args: { request?: { path: string } }) => {
        if (command === "api_request" && args.request) {
          const response = await fetch(args.request.path);
          const bytes = new Uint8Array(await response.arrayBuffer());
          return {
            status: response.status,
            contentType: response.headers.get("content-type"),
            body: btoa(String.fromCharCode(...bytes)),
          };
        }
        if (command !== "save_export") throw "unexpected_mock_ipc";
        win.exports.push({ command, args });
        return {
          filename: "ragagent-safe-report.md",
          destination: "Downloads",
        };
      },
    };
  });
  await page.getByRole("button", { name: "导出当前结果", exact: true }).click();
  await expect(
    page.getByText("已保存到系统下载目录：ragagent-safe-report.md", {
      exact: true,
    }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => (window as unknown as { exports: object[] }).exports,
    ),
  ).toEqual([
    {
      command: "save_export",
      args: { path: `/api/runs/${fixture.run_id}/exports/report.md` },
    },
  ]);
  await page
    .getByLabel("报告导出", { exact: true })
    .screenshot({ path: test.info().outputPath("report-exports.png") });
});
