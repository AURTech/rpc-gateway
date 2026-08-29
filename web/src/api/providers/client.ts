import { z } from "zod/v4";

import { api } from "@/api/client";
import { CHAINS, NETWORKS } from "@/lib/blockchain";

export const RPC_PROVIDER_VENDORS = [
  "alchemy",
  "quicknode",
  "chainstack",
  "drpc",
  "tenderly",
] as const;
export const RPC_PROVIDER_SYNC_STATUSES = [
  "never",
  "success",
  "partial",
  "failed",
] as const;
export const PROVIDER_ENDPOINT_SYNC_STATUSES = [
  "available",
  "missing",
] as const;
export const PROVIDER_ENDPOINT_DISCOVERY_STATUSES = [
  "present",
  "missing",
] as const;
export const PROVIDER_SYNC_RUN_STATES = [
  "queued",
  "running",
  "success",
  "partial",
  "failed",
] as const;
export type RpcProviderVendor = (typeof RPC_PROVIDER_VENDORS)[number];
export type RpcProviderSyncStatus = (typeof RPC_PROVIDER_SYNC_STATUSES)[number];
export type ProviderEndpointDiscoveryStatus =
  (typeof PROVIDER_ENDPOINT_DISCOVERY_STATUSES)[number];

const chainSchema = z.enum(CHAINS);
const networkSchema = z.enum(NETWORKS);
const vendorSchema = z.enum(RPC_PROVIDER_VENDORS);
const syncStatusSchema = z.enum(RPC_PROVIDER_SYNC_STATUSES);
const endpointSyncStatusSchema = z.enum(PROVIDER_ENDPOINT_SYNC_STATUSES);
const discoveryStatusSchema = z.enum(PROVIDER_ENDPOINT_DISCOVERY_STATUSES);
const syncRunStateSchema = z.enum(PROVIDER_SYNC_RUN_STATES);

const syncRunSchema = z.object({
  id: z.string(),
  trigger: z.enum(["manual", "scheduled"]),
  state: syncRunStateSchema,
  queued_at: z.string(),
  started_at: z.string().nullable(),
  endpoint_changes: z.number().int().nonnegative(),
  error: z.string().nullable(),
});

const networkPairSchema = z.object({
  chain: chainSchema,
  network: networkSchema,
});

const providerBaseSchema = z.object({
  id: z.string(),
  name: z.string(),
  vendor: vendorSchema,
  enabled: z.boolean(),
  sync_enabled: z.boolean(),
  credential: z.object({
    has_secret: z.boolean(),
  }),
  networks: z.array(networkPairSchema).nullable(),
  last_sync_at: z.string().nullable(),
  last_sync_status: syncStatusSchema,
  version: z.number().int().positive(),
  endpoint_counts: z.object({
    present: z.number().int().nonnegative(),
    missing: z.number().int().nonnegative(),
  }),
  connected_app_count: z.number().int().nonnegative(),
  syncing: z.boolean(),
});

const providerSchema = providerBaseSchema;

const providerCredentialDetailSchema = z.object({
  secret: z.string(),
});

const providerListSchema = z.object({
  page: z.number().int(),
  size: z.number().int(),
  total: z.number().int(),
  max_page: z.number().int(),
  items: z.array(providerSchema),
});

const endpointAuthSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("none"), has_secret: z.literal(false) }),
  z.object({ type: z.literal("bearer"), has_secret: z.literal(true) }),
  z.object({
    type: z.literal("header_api_key"),
    header_name: z.string(),
    has_secret: z.literal(true),
  }),
  z.object({
    type: z.literal("query_api_key"),
    query_param: z.string(),
    has_secret: z.literal(true),
  }),
  z.object({ type: z.literal("path_api_key"), has_secret: z.literal(true) }),
]);

const providerEndpointSchema = z.object({
  endpoint: z.object({
    id: z.string(),
    account_id: z.string(),
    name: z.string(),
    origin_type: z.literal("provider"),
    provider: z.object({
      id: z.string(),
      name: z.string(),
      vendor: vendorSchema,
      vendor_label: z.string(),
    }),
    provider_external_id: z.string(),
    provider_sync_status: endpointSyncStatusSchema,
    provider_last_seen_at: z.string().nullable(),
    chain: chainSchema,
    network: networkSchema,
    protocol: z.enum(["jsonrpc", "http_api"]),
    url: z.string(),
    effective_url: z.string().nullable(),
    enabled: z.boolean(),
    auth: endpointAuthSchema,
    version: z.number().int().positive(),
    created_at: z.string(),
    modified_at: z.string(),
  }),
  sync_status: endpointSyncStatusSchema,
  discovery_status: discoveryStatusSchema,
  registry_state: z.enum(["active", "archived"]),
  retained_by_routes: z.boolean(),
  external_id: z.string(),
  last_seen_at: z.string().nullable(),
  missing_since: z.string().nullable(),
  archived_at: z.string().nullable(),
});

const providerEndpointListSchema = z.object({
  page: z.number().int(),
  size: z.number().int(),
  total: z.number().int(),
  max_page: z.number().int(),
  items: z.array(providerEndpointSchema),
});

const syncRunListSchema = z.object({
  page: z.number().int(),
  size: z.number().int(),
  total: z.number().int(),
  max_page: z.number().int(),
  items: z.array(syncRunSchema),
});

const deleteImpactSchema = z.object({
  connected_apps: z.number().int().nonnegative(),
  automatic_route_targets: z.number().int().nonnegative(),
  managed_endpoints: z.number().int().nonnegative(),
  would_detach: z.number().int().nonnegative(),
  would_archive: z.number().int().nonnegative(),
  would_retain: z.number().int().nonnegative(),
});

const deleteResultSchema = z.object({
  id: z.string(),
  version: z.number().int().positive(),
  deleted: z.boolean(),
  archived_endpoints: z.number().int().nonnegative(),
  retained_endpoints: z.number().int().nonnegative(),
  detached_endpoints: z.number().int().nonnegative(),
});

const envelope = <T extends z.ZodType>(data: T) =>
  z.object({ msg: z.string(), data });

export type RpcProviderBase = z.infer<typeof providerSchema>;
export type RpcProvider = RpcProviderBase;
export type ProviderCredentialDetail = z.infer<
  typeof providerCredentialDetailSchema
>;
export type RpcProviderList = z.infer<typeof providerListSchema>;
export type RpcProviderSyncRun = z.infer<typeof syncRunSchema>;
export type RpcProviderSyncRunList = z.infer<typeof syncRunListSchema>;
export type ProviderDeleteImpact = z.infer<typeof deleteImpactSchema>;
export type ListProviderEndpointsParams = {
  discovery_status?: ProviderEndpointDiscoveryStatus;
  q?: string;
  chain?: (typeof CHAINS)[number];
  network?: (typeof NETWORKS)[number];
  protocol?: "jsonrpc" | "http_api";
  retained_by_routes?: boolean;
  page?: number;
  size?: number;
};
export type ProviderEndpoint = z.infer<typeof providerEndpointSchema>;
export type ProviderEndpointList = z.infer<typeof providerEndpointListSchema>;
export type RpcProviderNetworkPair = z.infer<typeof networkPairSchema>;
export type ProviderDeleteResult = z.infer<typeof deleteResultSchema>;

export type ProviderSettingsInput = {
  tag_ids?: number[] | null;
  tag_labels?: string[] | null;
  project?: string | null;
  organization?: string | null;
  region?: string | null;
  provider?: string | null;
  type?: string | null;
};

export type CreateProviderInput = {
  name: string;
  vendor: RpcProviderVendor;
  enabled?: boolean;
  sync_enabled?: boolean;
  credential: { secret: string };
  settings?: ProviderSettingsInput;
  networks?: RpcProviderNetworkPair[] | null;
};

export type UpdateProviderInput = Partial<{
  name: string;
  enabled: boolean;
  sync_enabled: boolean;
  credential: { secret: string };
  settings: ProviderSettingsInput;
  networks: RpcProviderNetworkPair[] | null;
}> & { expected_version: number };

export type DeleteProviderInput = {
  delete_unreferenced_endpoints?: boolean;
};

export type ListProvidersParams = {
  q?: string;
  vendor?: RpcProviderVendor | RpcProviderVendor[];
  enabled?: boolean;
  sync_enabled?: boolean;
  last_sync_status?: RpcProviderSyncStatus;
  page?: number;
  size?: number;
};

function buildListParams(
  input: ListProvidersParams,
): Record<string, string | string[]> {
  const params: Record<string, string | string[]> = {};
  if (input.q) params.q = input.q;
  if (input.vendor !== undefined) params.vendor = input.vendor;
  if (input.enabled !== undefined) params.enabled = String(input.enabled);
  if (input.sync_enabled !== undefined)
    params.sync_enabled = String(input.sync_enabled);
  if (input.last_sync_status !== undefined)
    params.last_sync_status = input.last_sync_status;
  if (input.page) params.page = String(input.page);
  if (input.size) params.size = String(input.size);
  return params;
}

export async function listProviders(
  input: ListProvidersParams = {},
): Promise<RpcProviderList> {
  const response = await api.get<unknown>("/v2/providers", {
    params: buildListParams(input),
  });
  return envelope(providerListSchema).parse(response).data;
}

export async function createProvider(
  input: CreateProviderInput,
): Promise<RpcProvider> {
  const response = await api.post<unknown>("/v2/providers", input, {
    cache: "no-store",
  });
  return envelope(providerSchema).parse(response).data;
}

export async function getProviderCredential(
  id: string,
): Promise<ProviderCredentialDetail> {
  const response = await api.get<unknown>(`/v2/providers/${id}/credential`, {
    cache: "no-store",
  });
  return envelope(providerCredentialDetailSchema).parse(response).data;
}

export async function updateProvider(
  id: string,
  input: UpdateProviderInput,
): Promise<RpcProvider> {
  const response = await api.patch<unknown>(`/v2/providers/${id}`, input, {
    cache: "no-store",
  });
  return envelope(providerSchema).parse(response).data;
}

export async function deleteProvider(
  id: string,
  input: DeleteProviderInput = {},
): Promise<ProviderDeleteResult> {
  const params = input.delete_unreferenced_endpoints
    ? { delete_unreferenced_endpoints: "true" }
    : undefined;
  const response = await api.delete<unknown>(`/v2/providers/${id}`, {
    params,
  });
  return envelope(deleteResultSchema).parse(response).data;
}

export async function syncProvider(id: string): Promise<RpcProviderSyncRun> {
  const response = await api.post<unknown>(`/v2/providers/${id}/sync`);
  return envelope(syncRunSchema).parse(response).data;
}

export async function listProviderSyncRuns(
  id: string,
  input: { page?: number; size?: number } = {},
): Promise<RpcProviderSyncRunList> {
  const response = await api.get<unknown>(`/v2/providers/${id}/sync-runs`, {
    params: {
      ...(input.page ? { page: String(input.page) } : {}),
      ...(input.size ? { size: String(input.size) } : {}),
    },
    cache: "no-store",
  });
  return envelope(syncRunListSchema).parse(response).data;
}

export async function getProviderSyncRun(
  id: string,
  runId: string,
): Promise<RpcProviderSyncRun> {
  const response = await api.get<unknown>(
    `/v2/providers/${id}/sync-runs/${runId}`,
    { cache: "no-store" },
  );
  return envelope(syncRunSchema).parse(response).data;
}

export async function getProviderDeleteImpact(
  id: string,
): Promise<ProviderDeleteImpact> {
  const response = await api.get<unknown>(`/v2/providers/${id}/delete-impact`, {
    cache: "no-store",
  });
  return envelope(deleteImpactSchema).parse(response).data;
}

export async function listProviderEndpoints(
  id: string,
  input: ListProviderEndpointsParams = {},
): Promise<ProviderEndpointList> {
  const response = await api.get<unknown>(`/v2/providers/${id}/endpoints`, {
    params: {
      ...(input.page ? { page: String(input.page) } : {}),
      ...(input.size ? { size: String(input.size) } : {}),
      ...(input.discovery_status
        ? { discovery_status: input.discovery_status }
        : {}),
      ...(input.q ? { q: input.q } : {}),
      ...(input.chain ? { chain: input.chain } : {}),
      ...(input.network ? { network: input.network } : {}),
      ...(input.protocol ? { protocol: input.protocol } : {}),
      ...(input.retained_by_routes ? { retained_by_routes: "true" } : {}),
    },
    cache: "no-store",
  });
  return envelope(providerEndpointListSchema).parse(response).data;
}
