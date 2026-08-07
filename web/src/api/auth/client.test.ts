import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, mockFetch } from "@/test/fetch";

import { logout, passwordLogin, setPassword } from "./client";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("passwordLogin", () => {
  it("posts credentials to the login endpoint with included cookies", async () => {
    const fetchMock = mockFetch(async () =>
      jsonResponse({
        msg: "ok",
        data: {
          identity_type: "user",
          id: "u1",
          email: "member@example.com",
          expires_at: "2026-06-05T00:00:00Z",
        },
      }),
    );

    await passwordLogin({ email: "member@example.com", password: "secret123" });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/v2/auth/login"),
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({
          email: "member@example.com",
          password: "secret123",
        }),
      }),
    );
  });
});

describe("setPassword", () => {
  it("posts the new password to the password endpoint", async () => {
    const fetchMock = mockFetch(async () =>
      jsonResponse({ msg: "ok", data: { updated: true } }),
    );

    await setPassword({ new_password: "fresh-pass-123" });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/v2/auth/password"),
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ new_password: "fresh-pass-123" }),
      }),
    );
  });
});

describe("logout", () => {
  it("accepts only a confirmed server-side logout", async () => {
    mockFetch(async () =>
      jsonResponse({ msg: "ok", data: { logged_out: true } }),
    );

    await expect(logout()).resolves.toBeUndefined();
  });

  it("rejects an unconfirmed logout response", async () => {
    mockFetch(async () =>
      jsonResponse({ msg: "not logged out", data: { logged_out: false } }),
    );

    await expect(logout()).rejects.toThrow();
  });
});
