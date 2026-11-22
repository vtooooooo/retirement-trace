import { test } from "node:test";
import assert from "node:assert/strict";
import { onRequest } from "../functions/api/[[path]].js";

const env = {
  API_ORIGIN: "https://backend.example",
  PT_EDGE_SECRET: "x".repeat(32),
};

test("proxy preserves cookies and original origin against a fixed upstream", async (t) => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url.href, "https://backend.example/api/v1/session?q=1");
    assert.equal(options.headers.get("origin"), "https://app.example");
    assert.equal(options.headers.get("x-pt-edge-secret"), env.PT_EDGE_SECRET);
    assert.equal(options.headers.get("x-pt-client-ip"), "192.0.2.1");
    assert.equal(options.redirect, "manual");
    return new Response("{}", {
      headers: {
        "Set-Cookie": "__Host-pt_session=test; Secure; Path=/; HttpOnly",
      },
    });
  });
  const request = new Request("https://app.example/api/v1/session?q=1", {
    method: "POST",
    body: "{}",
    headers: {
      Origin: "https://app.example",
      "CF-Connecting-IP": "192.0.2.1",
      "X-PT-Edge-Secret": "ignored",
    },
  });
  const response = await onRequest({ request, env });
  assert.equal(response.status, 200);
  assert.match(response.headers.get("set-cookie"), /__Host-pt_session/);
  assert.equal(response.headers.get("cache-control"), "no-store");
});

test("proxy rejects unknown paths, insecure configuration and oversized bodies", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", () =>
    assert.fail("Should not fetch"),
  );
  assert.equal(
    (
      await onRequest({
        request: new Request("https://app.example/api/other"),
        env,
      })
    ).status,
    404,
  );
  const api = "https://app.example/api/v1/session";
  assert.equal(
    (
      await onRequest({
        request: new Request(api),
        env: { ...env, API_ORIGIN: "http://insecure.example" },
      })
    ).status,
    503,
  );
  assert.equal(
    (
      await onRequest({
        request: new Request(api, { method: "POST", body: "x".repeat(8193) }),
        env,
      })
    ).status,
    413,
  );
  assert.equal(fetch.mock.callCount(), 0);
});
