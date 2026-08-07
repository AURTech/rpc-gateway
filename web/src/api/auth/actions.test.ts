import { afterEach, describe, expect, it } from "vitest";

import { getGoogleLoginUrl } from "./actions";

const originalApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

afterEach(() => {
  if (originalApiBaseUrl === undefined) {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    return;
  }

  process.env.NEXT_PUBLIC_API_BASE_URL = originalApiBaseUrl;
});

describe("getGoogleLoginUrl", () => {
  it("uses the local API base URL when none is configured", () => {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;

    expect(getGoogleLoginUrl()).toBe(
      "http://localhost:18173/v2/auth/google/login",
    );
  });

  it("trims a trailing slash from the configured API base URL", () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "https://api.example.test/";

    expect(getGoogleLoginUrl()).toBe(
      "https://api.example.test/v2/auth/google/login",
    );
  });

  it("supports a same-origin API proxy base URL", () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "/api";

    expect(getGoogleLoginUrl()).toBe("/api/v2/auth/google/login");
  });
});
