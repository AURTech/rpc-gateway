import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET, POST } from "./route";

const MAX_REQUEST_BODY_BYTES = 1024 * 1024;
const context = { params: Promise.resolve({ path: ["rpc", "call"] }) };

function chunkedRequest(
  chunks: Uint8Array[],
  headers?: HeadersInit,
): NextRequest {
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      const chunk = chunks.shift();
      if (chunk) {
        controller.enqueue(chunk);
      } else {
        controller.close();
      }
    },
  });
  const init: ConstructorParameters<typeof NextRequest>[1] & {
    duplex: "half";
  } = {
    method: "POST",
    headers,
    body,
    duplex: "half",
  };
  return new NextRequest("https://web.example.test/api/rpc/call", init);
}

describe("API proxy", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    vi.stubEnv("API_PROXY_TARGET", "https://api.example.test");
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.useRealTimers();
    fetchMock.mockReset();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("rejects an oversized declared content length before proxying", async () => {
    const req = new NextRequest("https://web.example.test/api/rpc/call", {
      method: "POST",
      headers: { "content-length": String(MAX_REQUEST_BODY_BYTES + 1) },
      body: "{}",
    });

    const response = await POST(req, context);

    expect(response.status).toBe(413);
    await expect(response.json()).resolves.toEqual({
      success: false,
      msg: "Request body exceeds the configured limit.",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("stops reading an undeclared chunked body when it crosses the limit", async () => {
    const req = chunkedRequest([
      new Uint8Array(MAX_REQUEST_BODY_BYTES),
      new Uint8Array([1]),
    ]);

    const response = await POST(req, context);

    expect(response.status).toBe(413);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns 408 when the absolute body-read deadline expires", async () => {
    vi.useFakeTimers();
    const body = new ReadableStream<Uint8Array>();
    const req = new NextRequest("https://web.example.test/api/rpc/call", {
      method: "POST",
      body,
      duplex: "half",
    } as ConstructorParameters<typeof NextRequest>[1] & { duplex: "half" });

    const responsePromise = POST(req, context);
    await vi.advanceTimersByTimeAsync(15_000);
    const response = await responsePromise;

    expect(response.status).toBe(408);
    await expect(response.json()).resolves.toEqual({
      success: false,
      msg: "Request body was not received in time.",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards a bounded request body unchanged", async () => {
    fetchMock.mockResolvedValue(new Response("ok", { status: 200 }));
    const req = chunkedRequest([
      new TextEncoder().encode("hello"),
      new TextEncoder().encode(" world"),
    ]);

    const response = await POST(req, context);

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledOnce();
    const [, init] = fetchMock.mock.calls[0];
    expect(new TextDecoder().decode(init?.body as ArrayBuffer)).toBe(
      "hello world",
    );
  });

  it("strips chunked transfer encoding and standard hop-by-hop headers", async () => {
    fetchMock.mockResolvedValue(new Response("ok", { status: 200 }));
    const req = chunkedRequest([new TextEncoder().encode("{}")], {
      connection: "keep-alive",
      "keep-alive": "timeout=5",
      te: "trailers",
      trailer: "x-checksum",
      "transfer-encoding": "chunked",
      upgrade: "websocket",
    });

    const response = await POST(req, context);

    expect(response.status).toBe(200);
    const headers = fetchMock.mock.calls[0][1]?.headers as Headers;
    for (const name of [
      "connection",
      "keep-alive",
      "te",
      "trailer",
      "transfer-encoding",
      "upgrade",
    ]) {
      expect(headers.has(name)).toBe(false);
    }
  });

  it("strips headers named by Connection while preserving business headers", async () => {
    vi.stubEnv("CF_ACCESS_CLIENT_ID", "trusted-id");
    vi.stubEnv("CF_ACCESS_CLIENT_SECRET", "trusted-secret");
    fetchMock.mockResolvedValue(new Response("ok", { status: 200 }));
    const req = chunkedRequest([new TextEncoder().encode("{}")], {
      connection: "x-remove-me, x-another-hop",
      cookie: "rpc_gateway_session=session-value",
      origin: "https://web.example.test",
      "x-csrf-token": "csrf-value",
      "x-remove-me": "removed",
      "x-another-hop": "removed-too",
      "cf-access-client-id": "untrusted-id",
      "cf-access-client-secret": "untrusted-secret",
    });

    await POST(req, context);

    const headers = fetchMock.mock.calls[0][1]?.headers as Headers;
    expect(headers.has("x-remove-me")).toBe(false);
    expect(headers.has("x-another-hop")).toBe(false);
    expect(headers.get("cookie")).toBe("rpc_gateway_session=session-value");
    expect(headers.get("origin")).toBe("https://web.example.test");
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("cf-access-client-id")).toBe("trusted-id");
    expect(headers.get("cf-access-client-secret")).toBe("trusted-secret");
  });

  it("keeps GET requests bodyless", async () => {
    fetchMock.mockResolvedValue(new Response("ok", { status: 200 }));
    const req = new NextRequest("https://web.example.test/api/rpc/call", {
      method: "GET",
      headers: { "content-length": String(MAX_REQUEST_BODY_BYTES + 1) },
    });

    const response = await GET(req, context);

    expect(response.status).toBe(200);
    expect(fetchMock.mock.calls[0][1]?.body).toBeUndefined();
  });
});
