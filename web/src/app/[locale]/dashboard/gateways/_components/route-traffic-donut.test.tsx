import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RouteTrafficDonut } from "./route-traffic-donut";

vi.mock("next-intl", async () =>
  (await import("@/test/intl")).nextIntlMock({ separator: " " }),
);

const mocks = vi.hoisted(() => ({
  usage: vi.fn(),
}));

vi.mock("@/hooks/use-usage", () => ({
  useUsageByEndpointQuery: mocks.usage,
}));

vi.mock("@/hooks/use-endpoints", () => ({
  useEndpointsQuery: () => ({
    data: {
      items: [
        { id: "endpoint-1", name: "Primary", url: "https://primary.rpc" },
        { id: "endpoint-2", name: "Backup", url: "https://backup.rpc" },
      ],
    },
  }),
}));

const PROPS = {
  gatewayId: "gateway-1",
  routeId: "route-1",
  chain: "ethereum" as const,
  network: "mainnet" as const,
  configuredEndpointIds: ["endpoint-1", "endpoint-2"],
};

describe("RouteTrafficDonut", () => {
  beforeEach(() => {
    mocks.usage.mockReset();
    mocks.usage.mockReturnValue({
      data: {
        total_attempts: 11,
        items: [
          { endpoint_id: "endpoint-1", total_attempts: 8 },
          { endpoint_id: "endpoint-2", total_attempts: 3 },
        ],
      },
      isLoading: false,
      isError: false,
    });
  });

  it("shows actual endpoint attempts and the highlighted endpoint", async () => {
    render(<RouteTrafficDonut {...PROPS} />);

    const breakdown = screen.getByLabelText("breakdown");
    expect(breakdown).toBeVisible();
    expect(screen.getByText("https://primary.rpc")).toBeVisible();
    expect(screen.getByText("https://backup.rpc")).toBeVisible();
    expect(
      screen.getByRole("button", { name: /Primary.*73%.*8/ }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByRole("button", { name: /Backup.*27%.*3/ }),
    ).toHaveAttribute("aria-pressed", "false");
  });

  it("selects an endpoint from the traffic ranking", async () => {
    const user = userEvent.setup();
    render(<RouteTrafficDonut {...PROPS} />);

    const backup = screen.getByRole("button", { name: /Backup.*27%.*3/ });
    await user.click(backup);

    expect(backup).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByRole("button", { name: /Primary.*73%.*8/ }),
    ).toHaveAttribute("aria-pressed", "false");
  });

  it("marks endpoints outside the saved route as historical", () => {
    mocks.usage.mockReturnValue({
      data: {
        total_attempts: 15,
        items: [
          { endpoint_id: "endpoint-1", total_attempts: 8 },
          { endpoint_id: "historical-endpoint", total_attempts: 7 },
        ],
      },
      isLoading: false,
      isError: false,
    });
    render(<RouteTrafficDonut {...PROPS} />);

    expect(
      screen.getByRole("button", {
        name: /historical-endpoint.*historical.*47%.*7/i,
      }),
    ).toBeVisible();
  });

  it("changes the usage time range with the segmented control", async () => {
    const user = userEvent.setup();
    render(<RouteTrafficDonut {...PROPS} />);

    await user.click(screen.getByRole("radio", { name: "range.weekly" }));

    expect(mocks.usage).toHaveBeenLastCalledWith(
      {
        gateway_id: "gateway-1",
        route_id: "route-1",
        range: "weekly",
      },
      { enabled: true },
    );
  });

  it("does not query an unsaved rule", () => {
    render(<RouteTrafficDonut {...PROPS} routeId={null} />);

    expect(screen.getByText("saveFirst")).toBeVisible();
    expect(mocks.usage).toHaveBeenCalledWith(
      { gateway_id: "gateway-1", route_id: "", range: "daily" },
      { enabled: false },
    );
  });
});
