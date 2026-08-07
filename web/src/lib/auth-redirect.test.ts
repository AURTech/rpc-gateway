import { describe, expect, it } from "vitest";

import { authRedirectPath } from "@/lib/auth-redirect";

const routing = {
  locales: ["en"] as const,
  defaultLocale: "en" as const,
};

function redirectPath(pathname: string, hasSession: boolean) {
  return authRedirectPath({ pathname, hasSession, ...routing });
}

describe("authRedirectPath", () => {
  it("keeps the login page reachable when a stale session cookie exists", () => {
    expect(redirectPath("/en/login", true)).toBeNull();
  });

  it("redirects authenticated root visits to the dashboard", () => {
    expect(redirectPath("/", true)).toBe("/en/dashboard");
  });

  it("redirects unauthenticated dashboard visits to login", () => {
    expect(redirectPath("/en/dashboard", false)).toBe("/en/login");
  });

  it("does not treat removed admin routes as an authenticated surface", () => {
    expect(redirectPath("/en/admin", false)).toBeNull();
    expect(redirectPath("/en/admin/accounts", false)).toBeNull();
    expect(redirectPath("/en/admin/config", true)).toBeNull();
  });

  it("protects migrated admin dashboard routes through the dashboard surface", () => {
    expect(redirectPath("/en/dashboard/accounts", false)).toBe("/en/login");
  });

  it("keeps the auth callback reachable in both auth states", () => {
    expect(redirectPath("/en/auth/callback", false)).toBeNull();
    expect(redirectPath("/en/auth/callback", true)).toBeNull();
  });
});
