import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createMethodRoute,
  deleteMethodRoute,
  type JsonRpcMethodRouteList,
  type JsonRpcRoute,
  updateMethodRoute,
} from "@/api/jsonrpc-routes/client";
import { createTestQueryClient, queryWrapper } from "@/test/query";

import {
  routesKeys,
  useCreateMethodRouteMutation,
  useDeleteMethodRouteMutation,
  useUpdateMethodRouteMutation,
} from "./use-routes";

vi.mock("@/api/jsonrpc-routes/client", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/api/jsonrpc-routes/client")>();
  return {
    ...actual,
    createMethodRoute: vi.fn(),
    updateMethodRoute: vi.fn(),
    deleteMethodRoute: vi.fn(),
  };
});

const ROUTE: JsonRpcRoute = {
  id: "route_1",
  gateway_id: "gateway_1",
  methods: ["eth_call"],
  is_default: false,
  max_attempts: 3,
  retry_policy: "safe_only",
  strategy: {
    type: "priority_failover",
    targets: [{ endpoint_id: "endpoint_1", position: 0 }],
  },
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  modified_at: "2026-01-01T00:00:00Z",
};

const SECOND_ROUTE: JsonRpcRoute = {
  ...ROUTE,
  id: "route_2",
  methods: ["eth_chainId"],
};

function setup<T>(hook: () => T, items: JsonRpcRoute[] = [ROUTE]) {
  const queryClient = createTestQueryClient();
  queryClient.setQueryData<JsonRpcMethodRouteList>(
    routesKeys.methods("gateway_1"),
    { total: items.length, items },
  );
  return {
    queryClient,
    ...renderHook(hook, { wrapper: queryWrapper(queryClient) }),
  };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("method route mutations", () => {
  it("inserts a created rule into the methods cache before revalidation", async () => {
    vi.mocked(createMethodRoute).mockResolvedValue(SECOND_ROUTE);
    const { queryClient, result } = setup(useCreateMethodRouteMutation);

    await act(async () => {
      await result.current.mutateAsync({
        gatewayId: "gateway_1",
        input: {
          methods: SECOND_ROUTE.methods,
          max_attempts: SECOND_ROUTE.max_attempts,
          retry_policy: SECOND_ROUTE.retry_policy,
          strategy: {
            type: "priority_failover",
            targets: [{ endpoint_id: "endpoint_1" }],
          },
        },
      });
    });

    expect(
      queryClient.getQueryData<JsonRpcMethodRouteList>(
        routesKeys.methods("gateway_1"),
      ),
    ).toEqual({ total: 2, items: [ROUTE, SECOND_ROUTE] });
  });

  it("replaces an updated rule in place before revalidation", async () => {
    const updated = { ...ROUTE, methods: ["eth_getBalance"], version: 2 };
    vi.mocked(updateMethodRoute).mockResolvedValue(updated);
    const { queryClient, result } = setup(useUpdateMethodRouteMutation, [
      ROUTE,
      SECOND_ROUTE,
    ]);

    await act(async () => {
      await result.current.mutateAsync({
        gatewayId: "gateway_1",
        routeId: ROUTE.id,
        input: {
          methods: updated.methods,
          max_attempts: updated.max_attempts,
          retry_policy: updated.retry_policy,
          strategy: {
            type: "priority_failover",
            targets: [{ endpoint_id: "endpoint_1" }],
          },
          expected_version: ROUTE.version,
        },
      });
    });

    expect(
      queryClient.getQueryData<JsonRpcMethodRouteList>(
        routesKeys.methods("gateway_1"),
      ),
    ).toEqual({ total: 2, items: [updated, SECOND_ROUTE] });
  });

  it("removes a deleted rule and updates the cached total", async () => {
    vi.mocked(deleteMethodRoute).mockResolvedValue(ROUTE);
    const { queryClient, result } = setup(useDeleteMethodRouteMutation, [
      ROUTE,
      SECOND_ROUTE,
    ]);

    await act(async () => {
      await result.current.mutateAsync({
        gatewayId: "gateway_1",
        routeId: ROUTE.id,
        expectedVersion: ROUTE.version,
      });
    });

    expect(
      queryClient.getQueryData<JsonRpcMethodRouteList>(
        routesKeys.methods("gateway_1"),
      ),
    ).toEqual({ total: 1, items: [SECOND_ROUTE] });
  });
});
