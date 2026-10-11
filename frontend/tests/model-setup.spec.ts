import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { setupChat } from "./chat-fixtures";

// MOCK UI/HTTP only. No real provider requests, real keys or scientific scores.
async function setup(page: Page) {
  await setupChat(page);
  const roles = ["supervisor", "retriever", "analyst", "reviewer"];
  const fixture = {
    mapping: {
      agents: Object.fromEntries(
        roles.map((role) => [
          role,
          {
            provider: "openai",
            model: `MOCK-${role}`,
            api_base: null,
            api_key_env: "OPENAI_API_KEY",
            key_configured: true,
          },
        ]),
      ),
    },
    saves: [] as unknown[],
    tests: [] as { agent: string; check: string }[],
    failure: "",
    advertised: true,
  };
  await page.route("**/api/providers", async (route) => {
    if (route.request().method() === "PUT") {
      const payload = route.request().postDataJSON();
      fixture.saves.push(payload);
      fixture.mapping = payload;
      for (const role of roles)
        fixture.mapping.agents[role].key_configured = true;
      await route.fulfill({ json: { status: "saved" } });
    } else await route.fulfill({ json: fixture.mapping });
  });
  await page.route("**/api/providers/test", async (route) => {
    const body = route.request().postDataJSON();
    fixture.tests.push(body);
    if (fixture.failure)
      await route.fulfill({
        status: 503,
        json: { error_code: fixture.failure },
      });
    else
      await route.fulfill({
        json: {
          ok: true,
          model: fixture.mapping.agents.supervisor.model,
          model_advertised: fixture.advertised,
        },
      });
  });
  await page.goto("/#/settings");
  const wizard = page.getByRole("region", { name: "首次模型配置" });
  await expect(wizard).toBeVisible();
  return { fixture, wizard };
}

test("existing roles load without writes or tests; confirmed shortcut saves four defaults and survives reopen", async ({
  page,
}) => {
  const { fixture, wizard } = await setup(page);
  await expect(wizard.getByLabel("聊天模型名称")).toHaveValue(
    "MOCK-supervisor",
  );
  expect(fixture.saves).toEqual([]);
  expect(fixture.tests).toEqual([]);
  await wizard.getByLabel("服务商", { exact: true }).selectOption("deepseek");
  await wizard.getByLabel("聊天模型名称").fill("MOCK-user-owned-model");
  await wizard.getByRole("button", { name: "为四个角色保存此配置" }).click();
  expect(fixture.saves).toEqual([]);
  await page
    .getByRole("dialog", { name: "默认角色映射确认" })
    .getByRole("button", { name: "取消保存" })
    .click();
  expect(fixture.mapping.agents.reviewer.model).toBe("MOCK-reviewer");
  await wizard.getByRole("button", { name: "为四个角色保存此配置" }).click();
  await page
    .getByRole("dialog", { name: "默认角色映射确认" })
    .getByRole("button", { name: "确认保存四角色配置" })
    .click();
  await expect(wizard.getByText(/四个角色配置已保存/)).toBeVisible();
  expect(fixture.saves).toHaveLength(1);
  for (const model of Object.values(fixture.mapping.agents)) {
    expect(model.provider).toBe("deepseek");
    expect(model.model).toBe("MOCK-user-owned-model");
    expect(model.api_key_env).toBe("DEEPSEEK_API_KEY");
  }
  await page.reload();
  await expect(wizard.getByLabel("服务商", { exact: true })).toHaveValue(
    "deepseek",
  );
  await expect(wizard.getByLabel("聊天模型名称")).toHaveValue(
    "MOCK-user-owned-model",
  );
  expect(fixture.tests).toEqual([]);
  expect(fixture.saves).toHaveLength(1);
  expect(
    await page.evaluate(
      () => JSON.stringify(localStorage) + JSON.stringify(sessionStorage),
    ),
  ).not.toContain("MOCK-user-owned-model");
  await expect(wizard.locator('input[type="password"]')).toHaveCount(0);
});

test("directory success is distinct from inference; each test needs confirmation and cancel sends nothing", async ({
  page,
}) => {
  const { fixture, wizard } = await setup(page);
  await wizard
    .getByRole("button", { name: "检查模型连接", exact: true })
    .click();
  expect(fixture.tests).toEqual([]);
  await page
    .getByRole("dialog", { name: "模型测试确认" })
    .getByRole("button", { name: "取消测试" })
    .click();
  expect(fixture.tests).toEqual([]);
  await wizard
    .getByRole("button", { name: "检查模型连接", exact: true })
    .click();
  await page
    .getByRole("dialog", { name: "模型测试确认" })
    .getByRole("button", { name: "确认并开始连接测试" })
    .click();
  await expect(wizard.getByText("本次测试成功", { exact: true })).toBeVisible();
  await expect(
    wizard.locator(".model-states div").filter({ hasText: "模型可实际推理" }),
  ).toContainText("尚未测试");
  expect(fixture.tests).toEqual([{ agent: "supervisor", check: "connection" }]);
  await wizard
    .getByRole("button", { name: "测试模型推理（可能收费）" })
    .click();
  await expect(
    page.getByRole("dialog", { name: "模型测试确认" }),
  ).toContainText("可能产生费用");
  expect(fixture.tests).toHaveLength(1);
  await page
    .getByRole("dialog", { name: "模型测试确认" })
    .getByRole("button", { name: "确认并开始推理测试" })
    .click();
  await expect(
    wizard.getByText("本次固定测试通过；不代表科研质量", { exact: true }),
  ).toBeVisible();
  expect(fixture.tests).toHaveLength(2);
  await page.reload();
  await expect(
    wizard.locator(".model-states div").filter({ hasText: "连接测试成功" }),
  ).toContainText("尚未测试");
  expect(fixture.tests).toHaveLength(2);
});

for (const [code, guidance] of [
  ["provider_credential_rejected", "服务商拒绝了密钥"],
  ["provider_network_failed", "无法连接模型服务"],
  ["provider_catalog_unavailable", "不支持模型目录"],
]) {
  test(`safe recovery for ${code} keeps saved mapping and requires manual retry`, async ({
    page,
  }) => {
    const { fixture, wizard } = await setup(page);
    fixture.failure = code;
    await wizard
      .getByRole("button", { name: "检查模型连接", exact: true })
      .click();
    await page
      .getByRole("dialog", { name: "模型测试确认" })
      .getByRole("button", { name: "确认并开始连接测试" })
      .click();
    await expect(wizard.getByRole("status")).toContainText(guidance);
    expect(fixture.tests).toHaveLength(1);
    expect(fixture.saves).toEqual([]);
    fixture.failure = "";
    await wizard
      .getByRole("button", { name: "检查模型连接", exact: true })
      .click();
    expect(fixture.tests).toHaveLength(1);
    await page
      .getByRole("dialog", { name: "模型测试确认" })
      .getByRole("button", { name: "确认并开始连接测试" })
      .click();
    await expect(
      wizard.getByText("本次测试成功", { exact: true }),
    ).toBeVisible();
    expect(fixture.tests).toHaveLength(2);
  });
}

test("missing advertised model is not treated as proven inference failure", async ({
  page,
}) => {
  const { fixture, wizard } = await setup(page);
  fixture.advertised = false;
  await wizard
    .getByRole("button", { name: "检查模型连接", exact: true })
    .click();
  await page
    .getByRole("dialog", { name: "模型测试确认" })
    .getByRole("button", { name: "确认并开始连接测试" })
    .click();
  await expect(wizard.getByRole("alert")).toContainText("目录未列出当前模型");
  await expect(
    wizard.locator(".model-states div").filter({ hasText: "模型可实际推理" }),
  ).toContainText("尚未测试");
  expect(fixture.tests).toHaveLength(1);
});

test("dirty advanced mapping blocks shortcut and tests without resetting existing roles", async ({
  page,
}) => {
  const { fixture, wizard } = await setup(page);
  const advanced = page.getByRole("group", { name: "reviewer", exact: true });
  await advanced
    .getByLabel("model", { exact: true })
    .fill("MOCK-unsaved-reviewer");
  await expect(
    wizard.getByRole("button", { name: "检查模型连接", exact: true }),
  ).toBeDisabled();
  await expect(
    wizard.getByRole("button", { name: "为四个角色保存此配置" }),
  ).toBeDisabled();
  expect(fixture.saves).toEqual([]);
  expect(fixture.tests).toEqual([]);
  expect(fixture.mapping.agents.reviewer.model).toBe("MOCK-reviewer");
});
