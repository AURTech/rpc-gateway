import { afterEach, beforeEach, type Mock, vi } from "vitest";

/**
 * Replace global `fetch` with a mock for every test in the calling file, and
 * reset it afterwards. Call at module scope so the hooks attach to the file's
 * root suite.
 */
export function stubFetch(): Mock {
  const fetchMock = vi.fn();
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    fetchMock.mockReset();
    vi.unstubAllGlobals();
  });
  return fetchMock;
}

/**
 * Spy on global `fetch` with a concrete implementation. Pair with
 * `vi.restoreAllMocks()` when a test needs to drive the request itself rather
 * than queue responses.
 */
export function mockFetch(impl: typeof fetch) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(impl);
}

/** A JSON response carrying `body` verbatim; 200 unless `init` says otherwise. */
export function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    ...init,
    headers: { "Content-Type": "application/json", ...init.headers },
  });
}

/**
 * A 200 response in the backend success envelope — `{ msg: "ok", data }`, see
 * `server/app/core/response.py`.
 */
export function okResponse(data: unknown): Response {
  return jsonResponse({ msg: "ok", data });
}
