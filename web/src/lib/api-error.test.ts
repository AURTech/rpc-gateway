import { describe, expect, it } from "vitest";

import { ApiError } from "@/api/client";

import { getApiErrorMessage, isAuthError } from "./api-error";

// Echoes the key so we can assert which translation was selected.
const t = (key: string) => `t:${key}`;

describe("getApiErrorMessage", () => {
  it("prefers the backend msg for HTTP errors", () => {
    const err = new ApiError({
      kind: "http",
      status: 400,
      data: { success: false, msg: "Gateway slug already exists" },
      message: "Gateway slug already exists",
    });
    expect(getApiErrorMessage(err, t)).toBe("Gateway slug already exists");
  });

  it("maps network failures to the offline key", () => {
    const err = new ApiError({ kind: "network", status: 0 });
    expect(getApiErrorMessage(err, t)).toBe("t:offline");
  });

  it("maps timeouts to the timeout key", () => {
    const err = new ApiError({ kind: "timeout", status: 0 });
    expect(getApiErrorMessage(err, t)).toBe("t:timeout");
  });

  it("maps 5xx without a body to the server key", () => {
    const err = new ApiError({ kind: "http", status: 502, data: null });
    expect(getApiErrorMessage(err, t)).toBe("t:server");
  });

  it("maps 401/403/404 to their keys when no body msg", () => {
    expect(
      getApiErrorMessage(new ApiError({ kind: "http", status: 401 }), t),
    ).toBe("t:unauthorized");
    expect(
      getApiErrorMessage(new ApiError({ kind: "http", status: 403 }), t),
    ).toBe("t:forbidden");
    expect(
      getApiErrorMessage(new ApiError({ kind: "http", status: 404 }), t),
    ).toBe("t:notFound");
  });

  it("falls back to generic for non-Error values", () => {
    expect(getApiErrorMessage("boom", t)).toBe("t:generic");
    expect(getApiErrorMessage(new Error("raw"), t)).toBe("t:generic");
  });
});

describe("isAuthError", () => {
  it("is true only for 401 ApiError", () => {
    expect(isAuthError(new ApiError({ kind: "http", status: 401 }))).toBe(true);
    expect(isAuthError(new ApiError({ kind: "http", status: 403 }))).toBe(
      false,
    );
    expect(isAuthError(new ApiError({ kind: "network", status: 0 }))).toBe(
      false,
    );
    expect(isAuthError(new Error("nope"))).toBe(false);
  });
});
