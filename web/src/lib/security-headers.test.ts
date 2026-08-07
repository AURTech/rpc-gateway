import { describe, expect, it } from "vitest";

import {
  buildContentSecurityPolicy,
  FIXED_SECURITY_HEADERS,
  productionContentSecurityPolicy,
} from "./security-headers";

describe("fixed security headers", () => {
  it("denies framing and browser capability sniffing", () => {
    const headers = Object.fromEntries(
      FIXED_SECURITY_HEADERS.map(({ key, value }) => [key, value]),
    );

    expect(headers).toMatchObject({
      "Referrer-Policy": "strict-origin-when-cross-origin",
      "X-Content-Type-Options": "nosniff",
      "X-Frame-Options": "DENY",
      "X-XSS-Protection": "0",
    });
    expect(headers["Permissions-Policy"]).toContain("camera=()");
    expect(headers["Permissions-Policy"]).toContain("microphone=()");
  });
});

describe("buildContentSecurityPolicy", () => {
  it("binds scripts to the request nonce and denies dangerous fallbacks", () => {
    const policy = buildContentSecurityPolicy({ nonce: "nonce-123" });

    expect(policy).toContain("script-src 'self' 'nonce-nonce-123'");
    expect(policy).toContain("script-src-attr 'none'");
    expect(policy).toContain("object-src 'none'");
    expect(policy).toContain("frame-ancestors 'none'");
    expect(policy).not.toContain("'unsafe-eval'");
  });

  it("extends connect-src with only an absolute HTTP API origin", () => {
    expect(
      buildContentSecurityPolicy({
        apiBaseUrl: "https://api.example.test/v2/",
        nonce: "n",
      }),
    ).toContain("connect-src 'self' https://api.example.test");

    for (const apiBaseUrl of ["/api", "not-a-url", "javascript:alert(1)"]) {
      expect(buildContentSecurityPolicy({ apiBaseUrl, nonce: "n" })).toContain(
        "connect-src 'self';",
      );
    }
  });
});

describe("productionContentSecurityPolicy", () => {
  it("does not enable nonce CSP outside production", () => {
    expect(
      productionContentSecurityPolicy({
        isProduction: false,
        nonce: "unused",
      }),
    ).toBeNull();
  });
});
