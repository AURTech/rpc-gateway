import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { middleware } from "./middleware";

vi.mock("next-intl/middleware", async () => {
  const { NextResponse } = await import("next/server");
  return {
    default: () => (req: Request) =>
      NextResponse.next({ request: { headers: new Headers(req.headers) } }),
  };
});

function request(pathname: string, options?: { authenticated?: boolean }) {
  return new NextRequest(`https://console.example.test${pathname}`, {
    headers: options?.authenticated
      ? { cookie: "rpc_gateway_session=session-value" }
      : undefined,
  });
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("middleware security policy", () => {
  it("propagates a production nonce through next-intl and the response", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.example.test/v1");

    const response = middleware(
      request("/en/dashboard", { authenticated: true }),
    );
    const policy = response.headers.get("Content-Security-Policy");
    const nonce = response.headers.get("x-middleware-request-x-nonce");

    expect(nonce).toBeTruthy();
    expect(policy).toContain(`'nonce-${nonce}'`);
    expect(policy).toContain("connect-src 'self' https://api.example.test");
    expect(
      response.headers.get("x-middleware-request-content-security-policy"),
    ).toBe(policy);
  });

  it("keeps authentication redirects while applying the production policy", () => {
    vi.stubEnv("NODE_ENV", "production");

    const response = middleware(request("/en/dashboard"));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "https://console.example.test/en/login",
    );
    expect(response.headers.get("Content-Security-Policy")).toContain(
      "script-src 'self' 'nonce-",
    );
  });

  it("leaves CSP disabled during development", () => {
    vi.stubEnv("NODE_ENV", "development");

    const response = middleware(
      request("/en/dashboard", { authenticated: true }),
    );

    expect(response.headers.has("Content-Security-Policy")).toBe(false);
    expect(response.headers.has("x-middleware-request-x-nonce")).toBe(false);
  });
});
