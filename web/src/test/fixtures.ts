import type { RpcGatewayBase, RpcGatewayList } from "@/api/gateways/client";

/**
 * Domain objects as the API clients hand them to components, already parsed.
 * Each builder fills every field the schema requires so a test only spells out
 * what it is actually about; pass the rest through `overrides`.
 *
 * These are deliberately not used by the `src/api/**` client tests: those feed
 * raw wire payloads through the schemas, which is the thing they exist to
 * check.
 */

export function makeGateway(
  overrides: Partial<RpcGatewayBase> = {},
): RpcGatewayBase {
  return {
    id: "gw_eth",
    name: "ethereum-mainnet",
    app_id: "app_1",
    app_name: "production",
    chain: "ethereum",
    network: "mainnet",
    enabled: true,
    effective_enabled: true,
    version: 1,
    access_points: [
      {
        transport: "jsonrpc",
        url: "https://eth-jsonrpc.example.test/{path_key}",
      },
    ],
    created_at: "2026-01-01T00:00:00Z",
    modified_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

/** A single-page gateway list, the shape `listGateways` resolves to. */
export function gatewayList(items: RpcGatewayBase[]): RpcGatewayList {
  return { page: 1, size: 50, total: items.length, max_page: 1, items };
}
