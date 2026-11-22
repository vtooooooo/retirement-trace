const allowedHeaders = [
  "accept",
  "content-type",
  "cookie",
  "idempotency-key",
  "origin",
];
const responseHeaders = [
  "content-type",
  "content-disposition",
  "retry-after",
  "x-content-type-options",
];
const BODY_LIMIT = 8 * 1024;

function reply(detail, status) {
  return Response.json(
    { detail },
    {
      status,
      headers: {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    },
  );
}

async function limitedBody(request) {
  if (!request.body) return undefined;
  const reader = request.body.getReader();
  const buffer = new Uint8Array(BODY_LIMIT);
  let used = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return buffer.subarray(0, used);
    if (used + value.byteLength > buffer.length) {
      await reader.cancel();
      return null;
    }
    buffer.set(value, used);
    used += value.byteLength;
  }
}

export async function onRequest({ request, env }) {
  const incoming = new URL(request.url);
  const readiness = incoming.pathname === "/api/ready";
  if (!readiness && !/^\/api\/v1\/[a-zA-Z0-9/_-]+$/.test(incoming.pathname)) {
    return reply("Unknown API path", 404);
  }
  if (
    !(readiness ? ["GET", "HEAD"] : ["GET", "HEAD", "POST", "DELETE"]).includes(
      request.method,
    )
  ) {
    return reply("Method not allowed", 405);
  }
  let upstream;
  try {
    upstream = new URL(env.API_ORIGIN);
    if (
      upstream.protocol !== "https:" ||
      upstream.origin !== env.API_ORIGIN ||
      !env.PT_EDGE_SECRET ||
      env.PT_EDGE_SECRET.length < 32
    ) {
      throw new Error();
    }
  } catch {
    return reply("API configuration is incomplete", 503);
  }
  upstream.pathname = readiness ? "/ready" : incoming.pathname;
  upstream.search = incoming.search;
  const headers = new Headers();
  for (const key of allowedHeaders) {
    const value = request.headers.get(key);
    if (value) headers.set(key, value);
  }
  headers.set("x-pt-edge-secret", env.PT_EDGE_SECRET);
  const client = request.headers.get("cf-connecting-ip");
  if (client) headers.set("x-pt-client-ip", client);

  try {
    const body = await limitedBody(request);
    if (body === null) return reply("Request body is too large", 413);
    const response = await fetch(upstream, {
      method: request.method,
      headers,
      body,
      redirect: "manual",
      signal: AbortSignal.timeout(20_000),
    });
    if (response.status >= 300 && response.status < 400)
      return reply("Unexpected API redirect", 502);
    const output = new Headers({
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "Strict-Transport-Security": "max-age=31536000",
      "Referrer-Policy": "no-referrer",
      "X-Frame-Options": "DENY",
    });
    for (const key of responseHeaders) {
      const value = response.headers.get(key);
      if (value) output.set(key, value);
    }
    const cookies =
      typeof response.headers.getSetCookie === "function"
        ? response.headers.getSetCookie()
        : response.headers.getAll("Set-Cookie");
    for (const value of cookies) output.append("Set-Cookie", value);
    return new Response(response.body, {
      status: response.status,
      headers: output,
    });
  } catch {
    return reply("API temporarily unavailable", 502);
  }
}
