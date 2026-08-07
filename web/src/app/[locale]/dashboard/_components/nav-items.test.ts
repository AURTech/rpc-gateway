import { describe, expect, it } from "vitest";

import { appIdFromPathname, buildDashboardNav } from "./nav-items";

describe("appIdFromPathname", () => {
  it("reads the app id when inside a specific app", () => {
    expect(appIdFromPathname("/dashboard/apps/app_1")).toBe("app_1");
    expect(appIdFromPathname("/dashboard/apps/app_1/gateways")).toBe("app_1");
  });

  it("treats the create route as Apps rather than an app named 'new'", () => {
    expect(appIdFromPathname("/dashboard/apps/new")).toBeNull();
  });

  it("returns null outside a specific app", () => {
    expect(appIdFromPathname("/dashboard/apps")).toBeNull();
    expect(appIdFromPathname("/dashboard")).toBeNull();
  });
});

describe("buildDashboardNav", () => {
  it("adds account administration without retired system configuration", () => {
    const items = buildDashboardNav({ isAdmin: true, appId: null });
    const settings = items.find((item) => item.key === "settings");

    expect(settings).toMatchObject({ exact: true });
    expect(settings?.children?.map((item) => item.key)).toEqual([
      "settingsProfile",
      "settingsSecurity",
    ]);
    expect(items.some((item) => item.key === "accounts")).toBe(true);
    expect(items.some((item) => item.key === "systemConfig")).toBe(false);
  });

  it("does not expose system configuration to regular users", () => {
    const items = buildDashboardNav({ isAdmin: false, appId: null });

    expect(items.some((item) => item.key === "systemConfig")).toBe(false);
    expect(items.map((item) => item.key)).toEqual([
      "overview",
      "apps",
      "endpoints",
      "providers",
      "usage",
      "settings",
    ]);
  });

  it("scopes the sidebar to the app with Overview as the app home", () => {
    const items = buildDashboardNav({ isAdmin: false, appId: "app_1" });

    expect(items.map((item) => item.key)).toEqual([
      "backToApps",
      "appOverview",
      "gateways",
      "appUsage",
      "appSettings",
    ]);
    expect(items[0]).toMatchObject({ back: true, href: "/dashboard/apps" });
    expect(items[1]).toMatchObject({
      href: "/dashboard/apps/app_1",
      exact: true,
    });
    expect(items[3]).toMatchObject({
      href: "/dashboard/apps/app_1/usage",
    });
  });
});
