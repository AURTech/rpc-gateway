import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, mockFetch } from "@/test/fetch";

import { ApiError, api } from "./client";

const originalApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
const SUCCESS_BODY = { success: true, data: null };

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  if (originalApiBaseUrl === undefined) {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    return;
  }
  process.env.NEXT_PUBLIC_API_BASE_URL = originalApiBaseUrl;
});

describe("api client", () => {
  it("uses the local API base URL when none is configured", async () => {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    const fetchMock = mockFetch(async () => jsonResponse(SUCCESS_BODY));

    await api.get("/v2/x");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:18173/v2/x",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("supports a same-origin API proxy base URL", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "/api";
    const fetchMock = mockFetch(async () => jsonResponse(SUCCESS_BODY));

    await api.get("/v2/x");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v2/x",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it.each([
    ["POST", () => api.post("/v2/x", { value: 1 })],
    ["PUT", () => api.put("/v2/x", { value: 1 })],
    ["PATCH", () => api.patch("/v2/x", { value: 1 })],
    ["DELETE", () => api.delete("/v2/x")],
  ])("adds the CSRF marker to %s requests", async (_method, request) => {
    const fetchMock = mockFetch(async () => jsonResponse(SUCCESS_BODY));

    await request();

    const init = fetchMock.mock.calls[0]?.[1];
    expect(new Headers(init?.headers).get("X-RPC-Gateway-CSRF")).toBe("1");
  });

  it("does not add the CSRF marker to safe requests", async () => {
    const fetchMock = mockFetch(async () => jsonResponse(SUCCESS_BODY));

    await api.get("/v2/x");

    const init = fetchMock.mock.calls[0]?.[1];
    expect(new Headers(init?.headers).has("X-RPC-Gateway-CSRF")).toBe(false);
  });

  it("surfaces the backend msg on HTTP errors", async () => {
    mockFetch(async () =>
      jsonResponse({ success: false, msg: "Slug taken" }, { status: 400 }),
    );

    const err = await api.get("/v2/x").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).kind).toBe("http");
    expect((err as ApiError).status).toBe(400);
    expect((err as ApiError).message).toBe("Slug taken");
    expect((err as ApiError).isClient).toBe(true);
  });

  it("classifies a fetch rejection as a network error", async () => {
    mockFetch(async () => {
      throw new TypeError("Failed to fetch");
    });

    const err = await api.get("/v2/x").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).kind).toBe("network");
  });

  it("classifies a timeout abort as a timeout error", async () => {
    mockFetch(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        }),
    );

    const err = await api.get("/v2/x", { timeoutMs: 10 }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).kind).toBe("timeout");
  });

  it("returns undefined for 204 No Content", async () => {
    mockFetch(async () => new Response(null, { status: 204 }));
    await expect(api.delete("/v2/x")).resolves.toBeUndefined();
  });

  it("exposes isUnauthorized for 401", async () => {
    mockFetch(async () =>
      jsonResponse({ success: false, msg: "no session" }, { status: 401 }),
    );
    const err = (await api.get("/v2/x").catch((e) => e)) as ApiError;
    expect(err.isUnauthorized).toBe(true);
  });
});
