import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { RpcGatewayDetail } from "@/api/gateways/client";
import type { HttpApiRoute } from "@/api/http-api-routes/client";

import { HttpApiRoutingSection } from "./http-api-routing-section";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());
vi.mock("sonner", async () => (await import("@/test/mocks")).sonnerMock());

const route: HttpApiRoute = {
  id: "route_1",
  gateway_id: "gateway_1",
  minimum_trust: "unverified",
  max_latency_ms: null,
  max_attempts: 3,
  retry_policy: "safe_only",
  strategy: { type: "priority_failover", targets: [] },
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  modified_at: "2026-01-01T00:00:00Z",
};

vi.mock("@/hooks/use-http-api-routes", () => ({
  useHttpApiRouteQuery: () => ({ data: route, isError: false }),
  useReplaceHttpApiRouteMutation: () => ({ isPending: false, mutate: vi.fn() }),
}));
vi.mock("./routing-mode-cards", () => ({
  RoutingModeCards: () => <div data-testid="routing-mode" />,
}));
vi.mock("./endpoint-pool-field", () => ({
  EndpointPoolField: ({ protocol }: { protocol?: string }) => (
    <div data-testid="endpoint-pool" data-protocol={protocol} />
  ),
}));

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
  access_points: [],
  created_at: "2026-01-01T00:00:00Z",
  modified_at: "2026-01-01T00:00:00Z",
};

describe("HttpApiRoutingSection", () => {
  it("renders an HTTP API endpoint pool without JSON-RPC method rules", async () => {
    render(<HttpApiRoutingSection gateway={gateway} />);

    await waitFor(() =>
      expect(screen.getByTestId("endpoint-pool")).toHaveAttribute(
        "data-protocol",
        "http_api",
      ),
    );
    expect(screen.getByTestId("routing-mode")).toBeInTheDocument();
    expect(screen.queryByTestId("method-picker")).not.toBeInTheDocument();
  });
});
