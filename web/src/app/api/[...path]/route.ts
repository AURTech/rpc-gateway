import type { NextRequest } from "next/server";

/**
 * Same-origin API proxy: the browser talks to the frontend origin (`/api/...`),
 * and this server-side handler forwards to the API. This keeps auth cookies
 * scoped to the web host instead of sharing them across API and web subdomains.
 *
 * Secrets (e.g. a Cloudflare Access service token) stay in server-only env and
 * are never exposed to the browser.
 */

export const dynamic = "force-dynamic";

const MAX_REQUEST_BODY_BYTES = 1024 * 1024;
const REQUEST_BODY_READ_TIMEOUT_MS = 15_000;

const HOP_BY_HOP_REQUEST_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

// Response headers that must not be copied verbatim when re-emitting the body.
const STRIPPED_RESPONSE_HEADERS = new Set([
  "content-encoding",
  "content-length",
  "transfer-encoding",
  "connection",
  "keep-alive",
  "set-cookie",
]);

function proxyTarget(): string | null {
  const target = process.env.API_PROXY_TARGET;
  return target ? target.replace(/\/$/, "") : null;
}

function isLocalHost(host: string): boolean {
  const hostname = host.split(":")[0];
  return hostname === "localhost" || hostname === "127.0.0.1";
}

function localizeSetCookie(cookie: string, req: NextRequest): string {
  let value = cookie.replace(/;\s*Domain=[^;]*/gi, "");

  if (isLocalHost(req.headers.get("host") ?? req.nextUrl.host)) {
    value = value
      .replace(/;\s*Secure/gi, "")
      .replace(/;\s*SameSite=None/gi, "; SameSite=Lax");
  }

  return value;
}

function requestBodyTooLarge(): Response {
  return Response.json(
    { success: false, msg: "Request body exceeds the configured limit." },
    { status: 413 },
  );
}

function requestBodyTimedOut(): Response {
  return Response.json(
    { success: false, msg: "Request body was not received in time." },
    { status: 408 },
  );
}

function declaredBodyTooLarge(req: NextRequest): boolean {
  const raw = req.headers.get("content-length");
  if (!raw || !/^\d+$/.test(raw)) {
    return false;
  }
  return Number(raw) > MAX_REQUEST_BODY_BYTES;
}

type BodyReadResult =
  | { body: ArrayBuffer }
  | { error: "timeout" | "too-large" };

async function readBoundedBody(req: NextRequest): Promise<BodyReadResult> {
  if (!req.body) {
    return { body: new ArrayBuffer(0) };
  }

  const reader = req.body.getReader();
  const chunks: Uint8Array[] = [];
  let totalBytes = 0;
  const deadline = Date.now() + REQUEST_BODY_READ_TIMEOUT_MS;

  try {
    while (true) {
      const remaining = deadline - Date.now();
      if (remaining <= 0) {
        await reader.cancel();
        return { error: "timeout" };
      }

      let timeoutId: ReturnType<typeof setTimeout> | undefined;
      const timeout = new Promise<"timeout">((resolve) => {
        timeoutId = setTimeout(() => resolve("timeout"), remaining);
      });
      const result = await Promise.race([reader.read(), timeout]);
      if (timeoutId !== undefined) clearTimeout(timeoutId);

      if (result === "timeout") {
        await reader.cancel();
        return { error: "timeout" };
      }

      const { done, value } = result;
      if (done) {
        break;
      }

      totalBytes += value.byteLength;
      if (totalBytes > MAX_REQUEST_BODY_BYTES) {
        await reader.cancel();
        return { error: "too-large" };
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }

  const body = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return { body: body.buffer };
}

function forwardedRequestHeaders(req: NextRequest): Headers {
  const headers = new Headers(req.headers);
  const connectionTokens = (headers.get("connection") ?? "")
    .split(",")
    .map((token) => token.trim().toLowerCase())
    .filter(Boolean);

  for (const header of HOP_BY_HOP_REQUEST_HEADERS) headers.delete(header);
  for (const token of connectionTokens) headers.delete(token);
  headers.delete("host");
  headers.delete("content-length");

  return headers;
}

async function forward(req: NextRequest, path: string[]): Promise<Response> {
  const target = proxyTarget();
  if (!target) {
    return Response.json(
      { success: false, msg: "API proxy target is not configured." },
      { status: 502 },
    );
  }

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  if (hasBody && declaredBodyTooLarge(req)) {
    return requestBodyTooLarge();
  }
  const bodyResult = hasBody ? await readBoundedBody(req) : undefined;
  if (bodyResult && "error" in bodyResult) {
    return bodyResult.error === "timeout"
      ? requestBodyTimedOut()
      : requestBodyTooLarge();
  }

  const url = `${target}/${path.join("/")}${req.nextUrl.search}`;

  const headers = forwardedRequestHeaders(req);

  const clientId = process.env.CF_ACCESS_CLIENT_ID;
  const clientSecret = process.env.CF_ACCESS_CLIENT_SECRET;
  if (clientId && clientSecret) {
    headers.set("CF-Access-Client-Id", clientId);
    headers.set("CF-Access-Client-Secret", clientSecret);
  }

  const upstream = await fetch(url, {
    method: req.method,
    headers,
    body: bodyResult?.body,
    redirect: "manual",
  });

  const responseHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!STRIPPED_RESPONSE_HEADERS.has(key.toLowerCase())) {
      responseHeaders.append(key, value);
    }
  });
  for (const cookie of upstream.headers.getSetCookie()) {
    responseHeaders.append("set-cookie", localizeSetCookie(cookie, req));
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

type RouteContext = { params: Promise<{ path: string[] }> };

async function handle(req: NextRequest, ctx: RouteContext): Promise<Response> {
  const { path } = await ctx.params;
  return forward(req, path);
}

export {
  handle as GET,
  handle as POST,
  handle as PUT,
  handle as PATCH,
  handle as DELETE,
  handle as OPTIONS,
  handle as HEAD,
};
