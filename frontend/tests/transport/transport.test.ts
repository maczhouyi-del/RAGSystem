/** Adapter unit tests: these exercise real transport encoding; no inference/GUI claims. */
import assert from "node:assert/strict";
import { afterEach, beforeEach, mock, test } from "node:test";
import {
  request,
  stream,
  openLocalResource,
  openPaperPdf,
  downloadReport,
} from "../../src/transport.ts";
import { errorMessage } from "../../src/errors.ts";

let commands: { command: string; args: Record<string, unknown> }[];
let native: (
  command: string,
  args: Record<string, unknown>,
) => Promise<unknown>;
beforeEach(() => {
  commands = [];
  native = async () => ({
    status: 200,
    contentType: "application/json",
    body: btoa('{"ok":true}'),
  });
  Object.assign(globalThis, {
    isTauri: true,
    window: {
      __TAURI_INTERNALS__: {
        invoke: async (command: string, args: Record<string, unknown>) => {
          commands.push({ command, args });
          return native(command, args);
        },
        transformCallback: () => 1,
        unregisterCallback: () => undefined,
      },
    },
  });
});
afterEach(() => {
  mock.restoreAll();
  Object.assign(globalThis, { isTauri: false });
});

test("desktop report exports send only a fixed route to the native saver", async () => {
  const id = "00000000-0000-4000-8000-000000000015";
  native = async () => ({
    filename: "safe-report.md",
    destination: "Downloads",
  });
  for (const format of [
    "report.md",
    "comparison.csv",
    "references.bib",
    "citations.json",
  ] as const) {
    assert.equal((await downloadReport(id, format)).destination, "Downloads");
    assert.deepEqual(commands.at(-1), {
      command: "save_export",
      args: { path: `/api/runs/${id}/exports/${format}` },
    });
  }
  const previous = commands.length;
  await assert.rejects(
    downloadReport("../escape", "report.md"),
    /local_export_not_allowed/,
  );
  await assert.rejects(
    downloadReport(id, "../escape" as "report.md"),
    /local_export_not_allowed/,
  );
  assert.equal(commands.length, previous);
});

test("native save failures stay safe and authorization can be recovered", async () => {
  const dispatched: string[] = [];
  Object.assign(window, {
    dispatchEvent: (event: Event) => {
      dispatched.push(event.type);
      return true;
    },
  });
  const id = "00000000-0000-4000-8000-000000000015";
  native = async () => {
    throw "local_auth_required";
  };
  await assert.rejects(downloadReport(id, "report.md"), /local_auth_required/);
  assert.deepEqual(dispatched, ["ragagent-auth-required"]);
  native = async () => {
    throw "PRIVATE_DATA Bearer SYNTHETIC";
  };
  await assert.rejects(
    downloadReport(id, "report.md"),
    /^Error: local_export_unavailable$/,
  );
});

test("web fetch remains same-origin and forwards abort signal", async () => {
  Object.assign(globalThis, { isTauri: false });
  const controller = new AbortController();
  const fetchMock = mock.method(
    globalThis,
    "fetch",
    async (path: string, options: RequestInit) => {
      assert.equal(path, "/api/conversations");
      assert.equal(options.signal, controller.signal);
      return new Response("[]", {
        headers: { "Content-Type": "application/json" },
      });
    },
  );
  assert.deepEqual(
    await (
      await request("/api/conversations", { signal: controller.signal })
    ).json(),
    [],
  );
  assert.equal(fetchMock.mock.callCount(), 1);
  assert.equal(commands.length, 0);
});

test("native unauthorized responses prompt pairing and never pass authorization through IPC", async () => {
  const dispatched: string[] = [];
  Object.assign(window, {
    dispatchEvent: (event: Event) => {
      dispatched.push(event.type);
      return true;
    },
  });
  native = async () => ({
    status: 401,
    contentType: "application/json",
    body: btoa('{"error_code":"local_auth_required"}'),
  });
  assert.equal((await request("/api/conversations")).status, 401);
  assert.deepEqual(dispatched, ["ragagent-auth-required"]);
  assert.ok(!JSON.stringify(commands).includes("Authorization"));
});

test("private raw error text is excluded from user-facing recovery messages", () => {
  const secret = "Bearer " + "SYNTHETIC".repeat(8);
  assert.ok(!errorMessage(secret).includes(secret));
  assert.match(errorMessage("provider_key_missing"), /聊天模型尚未配置/);
  assert.match(errorMessage("local_auth_required"), /本机授权/);
});
test("desktop request only passes allowed payload fields and decodes response", async () => {
  const response = await request("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: '{"title":"科研"}',
  });
  assert.deepEqual(await response.json(), { ok: true });
  const payload = commands[0].args.request as {
    path: string;
    body: string;
    contentType: string;
    method: string;
  };
  assert.equal(payload.path, "/api/conversations");
  assert.equal(payload.method, "POST");
  assert.equal(
    new TextDecoder().decode(
      Uint8Array.from(atob(payload.body), (c) => c.charCodeAt(0)),
    ),
    '{"title":"科研"}',
  );
});
test("desktop library searches preserve encoded Unicode and dots in query values", async () => {
  const parameters = new URLSearchParams({
    title: "中文..科学",
    author: "Alice DEMO",
    offset: "0",
    limit: "50",
  });
  const path = `/api/papers/search?${parameters}`;
  await request(path);
  const payload = commands[0].args.request as { path: string; method: string };
  assert.equal(payload.path, path);
  assert.equal(payload.method, "GET");
  assert.equal(
    new URL(`http://127.0.0.1${payload.path}`).searchParams.get("title"),
    "中文..科学",
  );
  await assert.rejects(
    request("/api/../papers/search?title=test"),
    /invalid_local_path/,
  );
});
test("multipart upload preserves actual boundary and PDF bytes", async () => {
  const form = new FormData();
  form.set(
    "file",
    new Blob(["%PDF-fixture"], { type: "application/pdf" }),
    "local.pdf",
  );
  await request("/api/papers/upload", { method: "POST", body: form });
  const payload = commands[0].args.request as {
    contentType: string;
    body: string;
  };
  const boundary = payload.contentType.split("boundary=")[1];
  assert.ok(boundary);
  assert.ok(atob(payload.body).includes(`--${boundary}`));
  assert.ok(atob(payload.body).includes("%PDF-fixture"));
});
test("desktop deletion preserves explicit confirmation and cleanup retry verbs", async () => {
  const id = "12345678-1234-1234-1234-123456789abc";
  const confirmation = {
    confirm_paper_id: id,
    expected_metadata_version: 2,
    scope: "current_library",
    acknowledge_retained_copies: true,
  };
  await request(`/api/papers/${id}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(confirmation),
  });
  await request(`/api/papers/${id}/deletion/retry`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  const first = commands[0].args.request as {
    path: string;
    method: string;
    body: string;
  };
  const retry = commands[1].args.request as {
    path: string;
    method: string;
    body: string;
  };
  assert.equal(first.path, `/api/papers/${id}`);
  assert.equal(first.method, "DELETE");
  assert.deepEqual(JSON.parse(atob(first.body)), confirmation);
  assert.equal(retry.path, `/api/papers/${id}/deletion/retry`);
  assert.equal(retry.method, "POST");
  assert.equal(atob(retry.body), "{}");
  assert.ok(!JSON.stringify(commands).includes("Authorization"));
});
test("desktop rejects arbitrary headers/destinations and aborted requests", async () => {
  await assert.rejects(
    request("https://remote.invalid/api/health"),
    /invalid_local_path/,
  );
  await assert.rejects(
    request("/api/health", { headers: { Authorization: "secret" } }),
    /local_header_not_allowed/,
  );
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(request("/api/health", { signal: controller.signal }), {
    name: "AbortError",
  });
  assert.equal(commands.length, 0);
});
test("request cancellation is sent and no raw native exception is forwarded", async () => {
  const controller = new AbortController();
  native = async (command) => {
    if (command === "api_request") {
      controller.abort();
      throw new Error("private debug detail");
    }
    return undefined;
  };
  await assert.rejects(request("/api/health", { signal: controller.signal }), {
    name: "AbortError",
  });
  assert.equal(commands[1].command, "cancel_request");
});
test("desktop empty responses preserve HTTP 204 semantics", async () => {
  native = async () => ({ status: 204, contentType: null, body: "" });
  assert.equal((await request("/api/conversations")).status, 204);
});
test("desktop event subscription forwards replay cursor and cancels once", () => {
  native = async () => undefined;
  const events: string[] = [];
  const close = stream(
    "/api/runs/12345678-1234-1234-1234-123456789abc/events",
    {
      after: 8,
      onExecution: (data, id) => events.push(`${id}:${data}`),
      onDone: () => undefined,
      onError: () => undefined,
    },
  );
  assert.equal(commands[0].args.after, 8);
  const channel = commands[0].args.onEvent as {
    onmessage: (event: unknown) => void;
  };
  channel.onmessage({ event: "execution", id: "9", data: "{}" });
  close();
  close();
  channel.onmessage({ event: "execution", id: "10", data: "{}" });
  assert.deepEqual(events, ["9:{}"]);
  assert.equal(
    commands.filter((v) => v.command === "cancel_request").length,
    1,
  );
});
test("desktop document opener only accepts local fixed resource URLs", async () => {
  const id = "12345678-1234-1234-1234-123456789abc";
  native = async () => undefined;
  await openLocalResource(`/api/papers/${id}/pdf#page=2`);
  assert.equal(commands[0].command, "open_resource");
  for (const path of [
    "https://evil.invalid/p.pdf",
    "file:///etc/passwd",
    `/api/papers/${id}/pdf?url=remote`,
    `/api/evaluations/${id}/secret.env`,
  ])
    await assert.rejects(openLocalResource(path), /local_resource_not_allowed/);
  assert.equal(commands.length, 1);
});
test("PDF navigation retains unknown pages and validates every explicit page before IPC", async () => {
  const id = "12345678-1234-1234-1234-123456789abc";
  native = async () => undefined;
  await openPaperPdf(id);
  await openPaperPdf(id, 7);
  assert.deepEqual(
    commands.map((item) => item.args.path),
    [`/api/papers/${id}/pdf`, `/api/papers/${id}/pdf#page=7`],
  );
  for (const page of [0, -1, 1.5, NaN, Infinity, 100000])
    await assert.rejects(openPaperPdf(id, page), /invalid_local_page/);
  await assert.rejects(
    openPaperPdf("../private", 7),
    /local_resource_not_allowed/,
  );
  assert.equal(commands.length, 2);
});

test("desktop organization scope and individual relations preserve exact verbs and confirmation", async () => {
  const id = "b27e97ba-0c6b-4ac2-8b1d-0ef2f6a8ef7f";
  const confirmation = { confirm_collection_id: id, expected_version: 2 };
  for (const [path, method, body] of [
    [`/api/papers/search?group=${id}&tag=${id}`, "GET", undefined],
    [`/api/papers/${id}/collections/${id}`, "PUT", undefined],
    [`/api/papers/${id}/collections/${id}`, "DELETE", undefined],
    [`/api/collections/${id}`, "DELETE", JSON.stringify(confirmation)],
  ] as const) {
    await request(path, {
      method,
      ...(body
        ? { body, headers: { "Content-Type": "application/json" } }
        : {}),
    });
    const payload = commands.at(-1)!.args.request as {
      path: string;
      method: string;
      body: string | null;
    };
    assert.equal(payload.path, path);
    assert.equal(payload.method, method);
    if (body) assert.deepEqual(JSON.parse(atob(payload.body!)), confirmation);
  }
  assert.ok(!JSON.stringify(commands).includes("Authorization"));
});

test("desktop annotation reads and coverage use fixed paths without inference", async () => {
  const id = "b27e97ba-0c6b-4ac2-8b1d-0ef2f6a8ef7f";
  const filters = { group_ids: [id], datasets: ["DEMO dataset"] };
  for (const [path, method, body] of [
    [`/api/papers/${id}/annotations?limit=50&offset=0`, "GET", undefined],
    [`/api/papers/${id}/chunks/${id}/source`, "GET", undefined],
    ["/api/annotations/coverage", "POST", JSON.stringify(filters)],
  ] as const) {
    await request(path, {
      method,
      ...(body
        ? { body, headers: { "Content-Type": "application/json" } }
        : {}),
    });
    const payload = commands.at(-1)!.args.request as {
      path: string;
      method: string;
      body: string | null;
    };
    assert.equal(payload.path, path);
    assert.equal(payload.method, method);
    if (body) assert.deepEqual(JSON.parse(atob(payload.body!)), filters);
  }
  assert.ok(!JSON.stringify(commands).includes("Authorization"));
});

test("desktop entity decisions retain source hash, Unicode offsets and explicit acknowledgement", async () => {
  const id = "b27e97ba-0c6b-4ac2-8b1d-0ef2f6a8ef7f";
  const body = {
    action: "correct",
    entity_type: "dataset",
    span_start: 2,
    span_end: 7,
    expected_version: 3,
    expected_content_sha256: "d".repeat(64),
  };
  for (const [path, method, payload] of [
    [`/api/papers/${id}/entity-mentions/${id}`, "PATCH", body],
    [
      `/api/papers/${id}/chunks/${id}/annotation-review`,
      "POST",
      {
        expected_content_sha256: "d".repeat(64),
        acknowledge_all_three_types_reviewed: true,
      },
    ],
    [
      `/api/papers/${id}/chunks/${id}/entities/${id}`,
      "DELETE",
      {
        expected_content_sha256: "d".repeat(64),
        acknowledge_remove_link: true,
      },
    ],
  ] as const) {
    await request(path, {
      method,
      body: JSON.stringify(payload),
      headers: { "Content-Type": "application/json" },
    });
    const actual = commands.at(-1)!.args.request as {
      path: string;
      method: string;
      body: string;
    };
    assert.equal(actual.path, path);
    assert.equal(actual.method, method);
    assert.deepEqual(JSON.parse(atob(actual.body)), payload);
  }
  assert.ok(!JSON.stringify(commands).includes("Authorization"));
});
