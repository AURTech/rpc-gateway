import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getUsageByEndpoint,
  getUsageByRoute,
  type RpcUsageByEndpoint,
  type RpcUsageByRoute,
} from "@/api/usage/client";
import { createTestQueryClient, queryWrapper } from "@/test/query";

import { useUsageByEndpointQuery, useUsageByRouteQuery } from "./use-usage";

vi.mock("@/api/usage/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/usage/client")>()),
  getUsageByEndpoint: vi.fn(),
  getUsageByRoute: vi.fn(),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((fulfill) => {
    resolve = fulfill;
  });
  return { promise, resolve };
}

const endpointUsage = {
  total_attempts: 11,
} as RpcUsageByEndpoint;

const routeUsage: RpcUsageByRoute = {
  time_range: "daily",
  granularity: "hourly",
  start_at: "2026-08-26T00:00:00Z",
  end_at: "2026-08-27T00:00:00Z",
  data_through: "2026-08-27T00:00:00Z",
  coverage_start_at: "2026-08-26T00:00:00Z",
  coverage_complete: true,
  items: [],
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("scope-bound usage queries", () => {
  it("clears endpoint data while a new route scope loads", async () => {
    const next = deferred<RpcUsageByEndpoint>();
    vi.mocked(getUsageByEndpoint).mockImplementation((params) =>
      params.route_id === "route-a"
        ? Promise.resolve(endpointUsage)
        : next.promise,
    );
    const client = createTestQueryClient();
    const hook = renderHook(
      ({ routeId }) =>
        useUsageByEndpointQuery({
          app_id: "app-1",
          gateway_id: "gateway-1",
          route_id: routeId,
          range: "daily",
        }),
      {
        initialProps: { routeId: "route-a" },
        wrapper: queryWrapper(client),
      },
    );

    await waitFor(() => expect(hook.result.current.data).toBe(endpointUsage));

    hook.rerender({ routeId: "route-b" });

    expect(hook.result.current.data).toBeUndefined();
    expect(hook.result.current.isPending).toBe(true);
  });

  it("clears route summary data while a new gateway scope loads", async () => {
    const next = deferred<RpcUsageByRoute>();
    vi.mocked(getUsageByRoute).mockImplementation((params) =>
      params.gateway_id === "gateway-a"
        ? Promise.resolve(routeUsage)
        : next.promise,
    );
    const client = createTestQueryClient();
    const hook = renderHook(
      ({ gatewayId }) =>
        useUsageByRouteQuery({
          app_id: "app-1",
          gateway_id: gatewayId,
          range: "daily",
        }),
      {
        initialProps: { gatewayId: "gateway-a" },
        wrapper: queryWrapper(client),
      },
    );

    await waitFor(() => expect(hook.result.current.data).toBe(routeUsage));

    hook.rerender({ gatewayId: "gateway-b" });

    expect(hook.result.current.data).toBeUndefined();
    expect(hook.result.current.isPending).toBe(true);
  });
});
