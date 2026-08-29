import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type AppOverviewTab, useAppOverviewTab } from "./use-app-overview-tab";

const { replaceMock } = vi.hoisted(() => ({ replaceMock: vi.fn() }));

vi.mock("@/i18n/navigation", async () =>
  (await import("@/test/navigation")).navigationMock({
    pathname: "/dashboard/apps/app_1",
    replace: replaceMock,
  }),
);

afterEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
});

describe("useAppOverviewTab", () => {
  it("preserves explicit tab choices across route updates", () => {
    window.localStorage.setItem(
      "rpc-gateway:app-overview-visited",
      JSON.stringify(["app_1"]),
    );

    const { result, rerender } = renderHook(
      ({ initialTab }: { initialTab?: AppOverviewTab }) =>
        useAppOverviewTab({ appId: "app_1", initialTab }),
      { initialProps: { initialTab: "gateways" as AppOverviewTab } },
    );

    rerender({ initialTab: "setup" });
    expect(result.current.tab).toBe("setup");

    act(() => result.current.changeTab("gateways"));
    expect(replaceMock).toHaveBeenLastCalledWith(
      "/dashboard/apps/app_1?tab=gateways",
    );

    act(() => result.current.changeTab("setup"));
    expect(result.current.tab).toBe("setup");
    expect(replaceMock).toHaveBeenLastCalledWith(
      "/dashboard/apps/app_1?tab=setup",
    );
  });
});
