import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { listGateways } from "@/api/gateways/client";
import { gatewayList, makeGateway } from "@/test/fixtures";
import { createTestQueryClient, renderWithQuery } from "@/test/query";

import { AppUsagePanel } from "./app-usage-panel";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

vi.mock("@/api/gateways/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/gateways/client")>();
  return { ...actual, listGateways: vi.fn() };
});

vi.mock("../../../usage/_components/usage-trend-cards", () => ({
  CacheByMethodTrendCard: (props: { scope: unknown; filters: unknown }) => (
    <div data-testid="cache-by-method-card">{JSON.stringify(props)}</div>
  ),
  CacheTrendCard: (props: { scope: unknown; filters: unknown }) => (
    <div data-testid="cache-card">{JSON.stringify(props)}</div>
  ),
  LatencyTrendCard: (props: { scope: unknown; filters: unknown }) => (
    <div data-testid="latency-card">{JSON.stringify(props)}</div>
  ),
  MethodTrendCard: (props: { scope: unknown; filters: unknown }) => (
    <div data-testid="method-card">{JSON.stringify(props)}</div>
  ),
  NetworkTrendCard: (props: { scope: unknown; filters: unknown }) => (
    <div data-testid="network-card">{JSON.stringify(props)}</div>
  ),
  OverallTrendCard: (props: { scope: unknown; filters: unknown }) => (
    <div data-testid="overall-card">{JSON.stringify(props)}</div>
  ),
  TrafficTrendCard: (props: { scope: unknown; filters: unknown }) => (
    <div data-testid="traffic-card">{JSON.stringify(props)}</div>
  ),
}));

const listGatewaysMock = vi.mocked(listGateways);

function renderPanel() {
  const client = createTestQueryClient();
  return renderWithQuery(<AppUsagePanel appId="app_1" />, client);
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("AppUsagePanel", () => {
  it("uses setup-style chain labels in the metrics gateway selector", async () => {
    listGatewaysMock.mockResolvedValue(
      gatewayList([
        makeGateway({}),
        makeGateway({
          id: "gw_sol",
          name: "solana-mainnet-beta",
          chain: "solana",
          network: "mainnet-beta",
          access_points: [
            {
              transport: "jsonrpc",
              url: "https://sol-jsonrpc.example.test/{path_key}",
            },
          ],
        }),
      ]),
    );
    const user = userEvent.setup();

    renderPanel();

    await waitFor(() =>
      expect(screen.getByTestId("method-card").textContent).toContain(
        '"app_id":"app_1"',
      ),
    );
    expect(screen.getByTestId("method-card")).toHaveTextContent(
      '"range":"weekly"',
    );
    expect(screen.getByTestId("network-card")).toBeInTheDocument();
    expect(screen.getByTestId("cache-card")).toBeInTheDocument();
    for (const card of [
      "overall-card",
      "cache-by-method-card",
      "traffic-card",
      "latency-card",
    ]) {
      expect(screen.getByTestId(card).textContent).toContain(
        '"app_id":"app_1"',
      );
    }
    expect(screen.getByText("allGateways")).toHaveClass("sr-only");
    expect(
      screen.getAllByRole("img", { name: "Ethereum" }).length,
    ).toBeGreaterThan(0);

    await user.click(screen.getByRole("combobox", { name: "gatewayLabel" }));

    expect(await screen.findByText("Ethereum Mainnet")).toBeInTheDocument();
    await user.click(screen.getByText("Solana Mainnet"));

    expect(screen.getByText("Solana Mainnet")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId("method-card").textContent).toContain(
        '"gateway_id":"gw_sol"',
      ),
    );
    for (const card of [
      "overall-card",
      "cache-by-method-card",
      "traffic-card",
      "latency-card",
    ]) {
      expect(screen.getByTestId(card).textContent).toContain(
        '"gateway_id":"gw_sol"',
      );
    }

    await user.click(
      screen.getByRole("radio", { name: "filters.ranges.hourly" }),
    );
    for (const card of [
      "overall-card",
      "method-card",
      "network-card",
      "cache-by-method-card",
      "cache-card",
      "traffic-card",
      "latency-card",
    ]) {
      expect(screen.getByTestId(card)).toHaveTextContent('"range":"hourly"');
    }
  });
});
