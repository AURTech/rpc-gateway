import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { RpcGatewayDetail } from "@/api/gateways/client";

import { GatewayDetailContent } from "./gateway-detail-content";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("@/i18n/navigation", async () =>
  (await import("@/test/navigation")).navigationMock({
    pathname: "/dashboard/apps/app_1/gateways/gateway_1",
    replace,
  }),
);

const gateway: RpcGatewayDetail = {
  id: "gateway_1",
  app_id: "app_1",
  app_name: "Example app",
  name: "TRON Mainnet",
  chain: "tron",
  network: "mainnet",
  enabled: true,
  effective_enabled: true,
  version: 1,
  access_points: [
    { transport: "jsonrpc", url: "https://example.test/jsonrpc" },
    { transport: "http_api", url: "https://example.test/http-api" },
  ],
  created_at: "2026-01-01T00:00:00Z",
  modified_at: "2026-01-01T00:00:00Z",
};

vi.mock("@/hooks/use-gateways", () => ({
  useGatewayQuery: () => ({ data: gateway, isLoading: false, isError: false }),
}));

vi.mock("./gateway-header", () => ({
  GatewayHeader: () => <div data-testid="gateway-header" />,
}));
vi.mock("./gateway-routing-section", () => ({
  GatewayRoutingSection: () => <div data-testid="jsonrpc-routing" />,
}));
vi.mock("./http-api-routing-section", () => ({
  HttpApiRoutingSection: () => <div data-testid="http-api-routing" />,
}));

describe("GatewayDetailContent", () => {
  it("opens the protocol selected on the gateway list", () => {
    render(
      <GatewayDetailContent
        appId="app_1"
        gatewayId="gateway_1"
        initialTransport="http_api"
      />,
    );

    expect(screen.getByTestId("http-api-routing")).toBeInTheDocument();
    expect(screen.queryByTestId("jsonrpc-routing")).not.toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "apiTypes.httpapi" }),
    ).toHaveAttribute("aria-selected", "true");
  });

  it("switches protocols and keeps the choice in the URL", async () => {
    const user = userEvent.setup();
    render(
      <GatewayDetailContent
        appId="app_1"
        gatewayId="gateway_1"
        initialTransport="jsonrpc"
      />,
    );

    await user.click(screen.getByRole("tab", { name: "apiTypes.httpapi" }));

    expect(screen.getByTestId("http-api-routing")).toBeInTheDocument();
    expect(replace).toHaveBeenCalledWith(
      "/dashboard/apps/app_1/gateways/gateway_1?transport=http_api",
    );
  });
});
