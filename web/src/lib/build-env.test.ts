import { describe, expect, it } from "vitest";

import { validateProductionBuildEnvironment } from "@/lib/build-env";

const directEnvironment = {
  NEXT_PUBLIC_API_BASE_URL: "https://api.example.test",
  NEXT_PUBLIC_SITE_URL: "https://rpc.example.test",
};

describe("validateProductionBuildEnvironment", () => {
  it("accepts an absolute API URL", () => {
    expect(() =>
      validateProductionBuildEnvironment(directEnvironment),
    ).not.toThrow();
  });

  it.each([
    "NEXT_PUBLIC_API_BASE_URL",
    "NEXT_PUBLIC_SITE_URL",
  ])("requires %s", (name) => {
    expect(() =>
      validateProductionBuildEnvironment({
        ...directEnvironment,
        [name]: "",
      }),
    ).toThrow(`Required production build variable ${name} is not set.`);
  });

  it("requires a proxy target for the same-origin API path", () => {
    expect(() =>
      validateProductionBuildEnvironment({
        ...directEnvironment,
        NEXT_PUBLIC_API_BASE_URL: "/api",
      }),
    ).toThrow(
      "Required production build variable API_PROXY_TARGET is not set.",
    );
  });

  it("accepts a same-origin API path with an absolute proxy target", () => {
    expect(() =>
      validateProductionBuildEnvironment({
        ...directEnvironment,
        NEXT_PUBLIC_API_BASE_URL: "/api",
        API_PROXY_TARGET: "http://rpc-gateway-api:18173",
      }),
    ).not.toThrow();
  });

  it.each([
    ["NEXT_PUBLIC_API_BASE_URL", "api.example.test"],
    ["NEXT_PUBLIC_SITE_URL", "/rpc"],
    ["API_PROXY_TARGET", "rpc-gateway-api:18173"],
  ])("rejects an invalid %s", (name, value) => {
    expect(() =>
      validateProductionBuildEnvironment({
        ...directEnvironment,
        NEXT_PUBLIC_API_BASE_URL:
          name === "API_PROXY_TARGET"
            ? "/api"
            : directEnvironment.NEXT_PUBLIC_API_BASE_URL,
        [name]: value,
      }),
    ).toThrow(`${name} must be an absolute HTTP(S) URL.`);
  });
});
