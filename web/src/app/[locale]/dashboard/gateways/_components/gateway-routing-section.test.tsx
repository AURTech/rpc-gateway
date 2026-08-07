import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { RpcGatewayDetail } from "@/api/gateways/client";
import type { JsonRpcRoute } from "@/api/jsonrpc-routes/client";

import { GatewayRoutingSection } from "./gateway-routing-section";

vi.mock("next-intl", async () =>
  (await import("@/test/intl")).nextIntlMock({ separator: " " }),
);

vi.mock("sonner", async () => (await import("@/test/mocks")).sonnerMock());

const deleteRuleMutate = vi.fn();

vi.mock("@/hooks/use-routes", () => ({
  useDefaultRouteQuery: () => ({ data: DEFAULT_ROUTE }),
  useMethodRoutesQuery: () => ({
    data: { total: 1, items: [METHOD_ROUTE] },
    isLoading: false,
    isError: false,
  }),
  useReplaceDefaultRouteMutation: () => ({
    isPending: false,
    mutate: vi.fn(),
  }),
  useCreateMethodRouteMutation: () => ({
    isPending: false,
    mutate: vi.fn(),
  }),
  useDeleteMethodRouteMutation: () => ({
    isPending: false,
    mutate: deleteRuleMutate,
  }),
}));

vi.mock("./method-multi-select", () => ({
  MethodMultiSelect: () => <div data-testid="method-picker" />,
}));

vi.mock("./routing-mode-cards", () => ({
  RoutingModeCards: () => <div data-testid="routing-mode" />,
}));

vi.mock("./endpoint-pool-field", () => ({
  EndpointPoolField: () => <div data-testid="endpoint-pool" />,
}));

const DEFAULT_ROUTE: JsonRpcRoute = {
  id: "route_default",
  gateway_id: "gateway_1",
  methods: [],
  is_default: true,
  minimum_trust: "unverified",
  max_latency_ms: null,
  max_attempts: 3,
  retry_policy: "safe_only",
  strategy: { type: "priority_failover", targets: [] },
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  modified_at: "2026-01-01T00:00:00Z",
};

const METHOD_ROUTE: JsonRpcRoute = {
  ...DEFAULT_ROUTE,
  id: "route_method",
  methods: ["eth_getBalance"],
  is_default: false,
  version: 2,
};

const GATEWAY: RpcGatewayDetail = {
  id: "gateway_1",
  app_id: "app_1",
  app_name: "Example app",
  name: "Ethereum Mainnet",
  chain: "ethereum",
  network: "mainnet",
  enabled: true,
  effective_enabled: true,
  version: 1,
  access_points: [],
  created_at: "2026-01-01T00:00:00Z",
  modified_at: "2026-01-01T00:00:00Z",
};

describe("GatewayRoutingSection", () => {
  beforeEach(() => {
    deleteRuleMutate.mockClear();
  });

  it("requires confirmation before deleting a method rule", async () => {
    const user = userEvent.setup();
    render(<GatewayRoutingSection gateway={GATEWAY} />);

    await user.click(
      screen.getByRole("button", { name: "methodRoutes.form.deleteRule" }),
    );

    expect(deleteRuleMutate).not.toHaveBeenCalled();
    expect(
      screen.getByRole("heading", {
        name: "methodRoutes.deleteDialog.title",
      }),
    ).toBeVisible();
    expect(
      screen.getByText("methodRoutes.deleteDialog.body eth_getBalance"),
    ).toBeVisible();

    await user.click(
      screen.getByRole("button", {
        name: "methodRoutes.deleteDialog.confirm",
      }),
    );

    expect(deleteRuleMutate).toHaveBeenCalledWith(
      {
        gatewayId: "gateway_1",
        routeId: "route_method",
        expectedVersion: 2,
      },
      expect.any(Object),
    );
  });
});
