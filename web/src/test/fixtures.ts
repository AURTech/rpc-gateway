import type { Endpoint } from "@/api/endpoints/client";
import type { RpcGatewayBase, RpcGatewayList } from "@/api/gateways/client";
import type { RpcProvider, RpcProviderBase } from "@/api/providers/client";

/**
 * Domain objects as the API clients hand them to components, already parsed.
 * Each builder fills every field the schema requires so a test only spells out
 * what it is actually about; pass the rest through `overrides`.
 *
 * These are deliberately not used by the `src/api/**` client tests: those feed
 * raw wire payloads through the schemas, which is the thing they exist to
 * check.
 */

export function makeEndpoint(overrides: Partial<Endpoint> = {}): Endpoint {
  return {
    id: "endpoint-1",
    account_id: "account-1",
    name: "primary",
    origin_type: "manual",
    provider: null,
    provider_external_id: null,
    provider_sync_status: null,
    provider_last_seen_at: null,
    chain: "ethereum",
    network: "mainnet",
    protocol: "jsonrpc",
    url: "https://rpc.example.com",
    enabled: true,
    auth: { type: "none", has_secret: false },
    version: 1,
    created_at: "2026-07-01T00:00:00Z",
    modified_at: "2026-07-01T00:00:00Z",
    ...overrides,
  };
}

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

export function makeProvider(
  overrides: Partial<RpcProviderBase> = {},
): RpcProviderBase {
  return {
    id: "prov_1",
    account_id: "acct_1",
    name: "alchemy-main",
    vendor: "alchemy",
    vendor_label: "Alchemy",
    enabled: true,
    sync_enabled: true,
    credential: { has_secret: true },
    settings: {},
    only_networks: [],
    ignore_networks: [],
    last_sync_at: null,
    last_sync_status: "never",
    last_sync_status_label: "Never",
    last_sync_error: null,
    last_sync_created: 0,
    last_sync_updated: 0,
    last_sync_restored: 0,
    last_sync_archived: 0,
    last_sync_skipped: 0,
    version: 1,
    created_at: "2026-07-01T00:00:00Z",
    modified_at: "2026-07-01T00:00:00Z",
    ...overrides,
  };
}

/** The detail projection, which unlike the list one carries the secret. */
export function makeProviderDetail(
  overrides: Partial<RpcProvider> = {},
): RpcProvider {
  return {
    ...makeProvider(),
    credential: { has_secret: true, secret: "provider-secret" },
    ...overrides,
  };
}
