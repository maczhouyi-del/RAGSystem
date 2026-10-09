import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { setupChat } from "./chat-fixtures";

// MOCK HTTP only. Real PostgreSQL scope/evidence/migration checks are separate.
type Label = {
  id: string;
  name: string;
  kind: "group" | "tag";
  version: number;
  paper_count: number;
};
async function setup(page: Page) {
  const sends: Record<string, unknown>[] = [];
  const chat = await setupChat(page, { onSend: (body) => sends.push(body) });
  const papers = [
    {
      id: randomUUID(),
      title: "MOCK first paper",
      authors: [],
      year: 2024,
      venue: null,
      status: "indexed",
      error_code: null,
      chunk_count: 3,
    },
    {
      id: randomUUID(),
      title: "MOCK second paper",
      authors: [],
      year: 2024,
      venue: null,
      status: "indexed",
      error_code: null,
      chunk_count: 2,
    },
  ];
  const labels = new Map<string, Label>(),
    members = new Map(papers.map((p) => [p.id, new Set<string>()]));
  const state = {
    writes: [] as {
      method: string;
      path: string;
      body: Record<string, unknown> | null;
    }[],
    searches: [] as URLSearchParams[],
    failRead: false,
    loseWrite: false,
    loseDelete: false,
    renameConflict: false,
  };
  function label(name: string, kind: Label["kind"] = "group") {
    const item = { id: randomUUID(), name, kind, version: 1, paper_count: 0 };
    labels.set(item.id, item);
    return item;
  }
  function values(ids?: Set<string>) {
    return [...labels.values()]
      .filter((c) => !ids || ids.has(c.id))
      .map((c) => ({
        ...c,
        paper_count: [...members.values()].filter((ids) => ids.has(c.id))
          .length,
      }));
  }
  await page.route("**/api/collections**", async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      id = url.pathname.split("/")[3],
      method = req.method();
    const body = req.postData() ? req.postDataJSON() : null;
    if (method !== "GET")
      state.writes.push({ method, path: url.pathname, body });
    if (method === "GET" && !id) {
      const all = values().sort(
        (a, b) => a.kind.localeCompare(b.kind) || a.name.localeCompare(b.name),
      );
      const limit = Number(url.searchParams.get("limit") ?? 200),
        offset = Number(url.searchParams.get("offset") ?? 0);
      await route.fulfill({
        json: {
          items: all.slice(offset, offset + limit),
          total: all.length,
          limit,
          offset,
        },
      });
      return;
    }
    if (method === "POST") {
      if (
        [...labels.values()].some(
          (c) =>
            c.kind === body.kind &&
            c.name.toLowerCase() === body.name.trim().toLowerCase(),
        )
      ) {
        await route.fulfill({
          status: 409,
          json: { error_code: "collection_name_conflict" },
        });
        return;
      }
      await route.fulfill({
        status: 201,
        json: label(body.name.trim(), body.kind),
      });
      return;
    }
    const current = labels.get(id);
    if (!current) {
      await route.fulfill({
        status: 404,
        json: { error_code: "collection_not_found" },
      });
      return;
    }
    if (method === "GET") {
      await route.fulfill({ json: values().find((c) => c.id === id) });
      return;
    }
    if (state.renameConflict && method === "PATCH") {
      state.renameConflict = false;
      current.name = "MOCK external rename";
      current.version++;
      await route.fulfill({
        status: 409,
        json: { error_code: "collection_version_conflict" },
      });
      return;
    }
    if (body.expected_version !== current.version) {
      await route.fulfill({
        status: 409,
        json: { error_code: "collection_version_conflict" },
      });
      return;
    }
    if (method === "PATCH") {
      current.name = body.name;
      current.version++;
      await route.fulfill({ json: values().find((c) => c.id === id) });
      return;
    }
    if (method === "DELETE") {
      labels.delete(id);
      for (const ids of members.values()) ids.delete(id);
      if (state.loseDelete) {
        state.loseDelete = false;
        await route.abort("failed");
      } else await route.fulfill({ status: 204 });
      return;
    }
    await route.fulfill({ status: 405 });
  });
  await page.route("**/api/papers/*/collections**", async (route) => {
    const req = route.request(),
      parts = new URL(req.url()).pathname.split("/"),
      pid = parts[3],
      cid = parts[5],
      method = req.method();
    if (method === "GET") {
      if (state.failRead)
        await route.fulfill({
          status: 503,
          json: { error_code: "infrastructure_unavailable" },
        });
      else await route.fulfill({ json: values(members.get(pid)) });
      return;
    }
    state.writes.push({ method, path: parts.join("/"), body: null });
    if (method === "PUT") members.get(pid)!.add(cid);
    else members.get(pid)!.delete(cid);
    if (state.loseWrite) {
      state.loseWrite = false;
      await route.abort("failed");
    } else await route.fulfill({ status: 204 });
  });
  await page.route("**/api/papers/search?*", async (route) => {
    const params = new URL(route.request().url()).searchParams;
    state.searches.push(params);
    const items = papers.filter(
      (p) =>
        (!params.get("group") ||
          (labels.get(params.get("group")!)?.kind === "group" &&
            members.get(p.id)!.has(params.get("group")!))) &&
        (!params.get("tag") ||
          (labels.get(params.get("tag")!)?.kind === "tag" &&
            members.get(p.id)!.has(params.get("tag")!))),
    );
    await route.fulfill({
      json: { items, total: items.length, limit: 50, offset: 0 },
    });
  });
  return { chat, sends, papers, labels, members, state, label };
}
const manager = (page: Page) =>
  page.getByLabel("分组与标签管理", { exact: true });
async function knowledge(page: Page) {
  await page.goto("/#/knowledge");
  await expect(
    page.getByRole("heading", { name: "Knowledge Base", exact: true }),
  ).toBeVisible();
}
async function openManager(page: Page) {
  await manager(page).getByText("管理论文分组与标签", { exact: true }).click();
  await expect(
    manager(page).getByRole("button", { name: "刷新分组与标签", exact: true }),
  ).toBeEnabled();
}
async function openPaper(page: Page, title: string) {
  const panel = page.getByLabel(`${title} 分组与标签`, { exact: true });
  await panel.getByText("分组与标签", { exact: true }).click();
  return panel;
}

test("create group and tag, duplicate name keeps draft without changing papers", async ({
  page,
}) => {
  const data = await setup(page);
  await knowledge(page);
  await openManager(page);
  const form = manager(page).getByRole("form", { name: "创建分组或标签" });
  await form.getByLabel("分组或标签名称").fill("MOCK project");
  await form.getByRole("button", { name: "创建", exact: true }).click();
  await expect(manager(page)).toContainText("分组 MOCK project 已保存");
  await form.getByLabel("分组或标签名称").fill("MOCK project");
  await form.getByRole("button", { name: "创建", exact: true }).click();
  await expect(manager(page).getByRole("alert")).toContainText("已有这个名称");
  await expect(form.getByLabel("分组或标签名称")).toHaveValue("MOCK project");
  await form.getByLabel("组织类型").selectOption("tag");
  await form.getByRole("button", { name: "创建", exact: true }).click();
  await expect(manager(page)).toContainText("标签 MOCK project 已保存");
  expect(data.labels.size).toBe(2);
  expect(data.papers.length).toBe(2);
});

test("one paper belongs to multiple groups and tags, reload and individual removal preserve other links", async ({
  page,
}) => {
  const data = await setup(page),
    a = data.label("MOCK A"),
    b = data.label("MOCK B"),
    t = data.label("MOCK reviewed", "tag");
  await knowledge(page);
  let panel = await openPaper(page, data.papers[0].title);
  for (const name of ["分组：MOCK A", "分组：MOCK B", "标签：MOCK reviewed"]) {
    await panel.getByRole("checkbox", { name, exact: true }).check();
    await expect(
      panel.getByRole("button", { name: "读取最新关联", exact: true }),
    ).toBeEnabled();
  }
  expect([...data.members.get(data.papers[0].id)!].sort()).toEqual(
    [a.id, b.id, t.id].sort(),
  );
  await page.reload();
  panel = await openPaper(page, data.papers[0].title);
  await expect(
    panel.getByRole("checkbox", { name: "分组：MOCK A", exact: true }),
  ).toBeChecked();
  await panel
    .getByRole("checkbox", { name: "分组：MOCK A", exact: true })
    .uncheck();
  await expect(
    panel.getByRole("button", { name: "读取最新关联", exact: true }),
  ).toBeEnabled();
  await expect(
    panel.getByRole("checkbox", { name: "分组：MOCK B", exact: true }),
  ).toBeChecked();
  expect([...data.members.get(data.papers[0].id)!].sort()).toEqual(
    [b.id, t.id].sort(),
  );
  expect(data.members.get(data.papers[1].id)!.size).toBe(0);
  await page.screenshot({
    path: test.info().outputPath("paper-organization.png"),
    fullPage: true,
  });
});

test("library group and tag selections are sent together to backend, deleted selected ID stays restrictive", async ({
  page,
}) => {
  const data = await setup(page),
    a = data.label("MOCK scope"),
    t = data.label("MOCK tag", "tag");
  data.members.get(data.papers[0].id)!.add(a.id);
  data.members.get(data.papers[0].id)!.add(t.id);
  data.members.get(data.papers[1].id)!.add(a.id);
  await knowledge(page);
  await openManager(page);
  const search = page.getByRole("form", { name: "文献搜索与筛选" });
  await search.getByLabel("筛选论文分组").selectOption(a.id);
  await search.getByLabel("筛选自定义标签").selectOption(t.id);
  await search.getByRole("button", { name: "搜索文献", exact: true }).click();
  await expect(page.getByLabel("文献分页")).toContainText("共 1 篇");
  expect(data.state.searches.at(-1)!.get("group")).toBe(a.id);
  expect(data.state.searches.at(-1)!.get("tag")).toBe(t.id);
  data.labels.delete(a.id);
  await manager(page)
    .getByRole("button", { name: "刷新分组与标签", exact: true })
    .click();
  await expect(search.getByLabel("筛选论文分组")).toHaveValue(a.id);
  await search.getByRole("button", { name: "搜索文献", exact: true }).click();
  await page
    .getByLabel("文献分页")
    .getByRole("button", { name: "刷新", exact: true })
    .click();
  await expect(page.getByLabel("文献分页")).toContainText("共 0 篇");
  expect(data.state.writes).toHaveLength(0);
});

test("rename conflict preserves draft and only explicit retry uses refreshed version", async ({
  page,
}) => {
  const data = await setup(page),
    a = data.label("MOCK project");
  await knowledge(page);
  await openManager(page);
  await manager(page)
    .getByLabel("修改 MOCK project 名称")
    .fill("MOCK intended rename");
  data.state.renameConflict = true;
  await manager(page)
    .getByRole("button", { name: "重命名分组 MOCK project", exact: true })
    .click();
  await expect(manager(page).getByRole("alert")).toContainText("已被修改");
  await expect(
    manager(page).getByLabel("修改 MOCK external rename 名称"),
  ).toHaveValue("MOCK intended rename");
  expect(data.state.writes).toHaveLength(1);
  await manager(page)
    .getByRole("button", {
      name: "重命名分组 MOCK external rename",
      exact: true,
    })
    .click();
  await expect(manager(page)).toContainText("分组 MOCK intended rename 已保存");
  expect(data.state.writes[1].body).toEqual({
    name: "MOCK intended rename",
    expected_version: 2,
  });
  expect(data.labels.get(a.id)!.version).toBe(3);
});

test("delete cancel and Escape write nothing, explicit deletion preserves paper and other groups", async ({
  page,
}) => {
  const data = await setup(page),
    a = data.label("MOCK A"),
    b = data.label("MOCK B");
  data.members.get(data.papers[0].id)!.add(a.id);
  data.members.get(data.papers[0].id)!.add(b.id);
  await knowledge(page);
  await openManager(page);
  const button = manager(page).getByRole("button", {
    name: "删除分组 MOCK A",
    exact: true,
  });
  await button.click();
  const dialog = page.getByRole("dialog", { name: "删除分组或标签确认" });
  await expect(dialog).toContainText("论文、PDF、向量和已有 Evidence 会保留");
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  await button.click();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  expect(data.state.writes).toHaveLength(0);
  await button.click();
  await dialog
    .getByRole("button", { name: "确认仅删除分组或标签", exact: true })
    .click();
  await expect(dialog).toHaveCount(0);
  expect(data.state.writes).toEqual([
    {
      method: "DELETE",
      path: `/api/collections/${a.id}`,
      body: { confirm_collection_id: a.id, expected_version: 1 },
    },
  ]);
  expect(data.papers.length).toBe(2);
  expect([...data.members.get(data.papers[0].id)!]).toEqual([b.id]);
});

test("lost membership response reads committed link without repeating write", async ({
  page,
}) => {
  const data = await setup(page),
    a = data.label("MOCK A");
  await knowledge(page);
  const panel = await openPaper(page, data.papers[0].title);
  data.state.loseWrite = true;
  await panel
    .getByRole("checkbox", { name: "分组：MOCK A", exact: true })
    .check();
  await expect(
    panel.getByRole("button", { name: "读取最新关联", exact: true }),
  ).toBeEnabled();
  await expect(
    panel.getByRole("checkbox", { name: "分组：MOCK A", exact: true }),
  ).toBeChecked();
  expect(data.members.get(data.papers[0].id)!.has(a.id)).toBe(true);
  expect(data.state.writes).toHaveLength(1);
});

test("failed membership read prevents mutation until explicit recovery", async ({
  page,
}) => {
  const data = await setup(page);
  data.label("MOCK A");
  data.state.failRead = true;
  await knowledge(page);
  const panel = await openPaper(page, data.papers[0].title);
  await expect(panel.getByRole("alert")).toContainText("数据库或 Redis 不可用");
  await expect(
    panel.getByRole("checkbox", { name: "分组：MOCK A", exact: true }),
  ).toBeDisabled();
  expect(data.state.writes).toHaveLength(0);
  data.state.failRead = false;
  await panel
    .getByRole("button", { name: "读取最新关联", exact: true })
    .click();
  await panel
    .getByRole("checkbox", { name: "分组：MOCK A", exact: true })
    .check();
  await expect(
    panel.getByRole("checkbox", { name: "分组：MOCK A", exact: true }),
  ).toBeChecked();
});

for (const mode of ["rag", "research"]) {
  test(`${mode} sends group/tag IDs with existing filters, New Chat clears visible organization scope`, async ({
    page,
  }) => {
    const data = await setup(page),
      a = data.label("MOCK A"),
      t = data.label("MOCK tag", "tag");
    await page.goto(`/#/${mode}`);
    const composer = page.locator(".chat-composer");
    await composer
      .getByText("文献过滤条件（同字段 OR，不同字段 AND）", { exact: true })
      .click();
    const scope = composer.getByLabel("科研项目检索范围");
    await scope
      .getByRole("button", { name: "刷新分组与标签", exact: true })
      .click();
    await scope
      .getByLabel("分组检索范围（可多选）", { exact: true })
      .selectOption([a.id]);
    await scope
      .getByLabel("标签检索范围（可多选）", { exact: true })
      .selectOption([t.id]);
    await composer.getByLabel("authors", { exact: true }).fill("MOCK Alice");
    await page.getByLabel("研究问题").fill("MOCK project question");
    await page.getByRole("button", { name: "发送", exact: true }).click();
    await expect(
      page.getByLabel("Assistant 消息", { exact: true }),
    ).toHaveCount(1);
    expect(data.sends[0].filters).toMatchObject({
      group_ids: [a.id],
      tag_ids: [t.id],
      authors: ["MOCK Alice"],
    });
    await page.getByRole("button", { name: "New Chat", exact: true }).click();
    await composer
      .getByText("文献过滤条件（同字段 OR，不同字段 AND）", { exact: true })
      .click();
    await expect(
      scope.getByLabel("分组检索范围（可多选）", { exact: true }),
    ).toHaveValues([]);
    await expect(
      scope.getByLabel("标签检索范围（可多选）", { exact: true }),
    ).toHaveValues([]);
  });
}

test("organization catalog supports more than 200 labels without discarding an unloaded selected scope", async ({
  page,
}) => {
  const data = await setup(page);
  for (let i = 0; i < 201; i++)
    data.label(`MOCK ${String(i).padStart(3, "0")}`);
  const last = [...data.labels.values()].at(-1)!;
  await page.goto("/#/rag");
  const composer = page.locator(".chat-composer");
  await composer
    .getByText("文献过滤条件（同字段 OR，不同字段 AND）", { exact: true })
    .click();
  const scope = composer.getByLabel("科研项目检索范围");
  await scope
    .getByRole("button", { name: "刷新分组与标签", exact: true })
    .click();
  await scope
    .getByRole("button", { name: "加载更多分组与标签", exact: true })
    .click();
  await scope
    .getByLabel("分组检索范围（可多选）", { exact: true })
    .selectOption(last.id);
  await scope
    .getByRole("button", { name: "刷新分组与标签", exact: true })
    .click();
  await expect(
    scope.getByLabel("分组检索范围（可多选）", { exact: true }),
  ).toHaveValues([last.id]);
  await expect(scope).toContainText("已选范围（未读取或已删除）");
});

test("lost delete response resolves through read-only absence check and never deletes a paper", async ({
  page,
}) => {
  const data = await setup(page),
    a = data.label("MOCK A");
  data.state.loseDelete = true;
  await knowledge(page);
  await openManager(page);
  await manager(page)
    .getByRole("button", { name: "删除分组 MOCK A", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "确认仅删除分组或标签", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(data.labels.has(a.id)).toBe(false);
  expect(data.state.writes).toHaveLength(1);
  expect(data.state.writes[0].path).toBe(`/api/collections/${a.id}`);
  expect(data.papers.length).toBe(2);
});

test("ambiguous membership with unavailable read stays locked until explicit status recovery", async ({
  page,
}) => {
  const data = await setup(page),
    a = data.label("MOCK A");
  await knowledge(page);
  const panel = await openPaper(page, data.papers[0].title);
  const checkbox = panel.getByRole("checkbox", {
    name: "分组：MOCK A",
    exact: true,
  });
  await expect(checkbox).toBeEnabled();
  data.state.loseWrite = true;
  data.state.failRead = true;
  await checkbox.check();
  await expect(panel.getByRole("alert")).toContainText("数据库或 Redis 不可用");
  await expect(checkbox).toBeDisabled();
  expect(data.state.writes).toHaveLength(1);
  expect(data.members.get(data.papers[0].id)!.has(a.id)).toBe(true);
  data.state.failRead = false;
  await panel
    .getByRole("button", { name: "读取最新关联", exact: true })
    .click();
  await expect(checkbox).toBeEnabled();
  await expect(checkbox).toBeChecked();
  expect(data.state.writes).toHaveLength(1);
});
