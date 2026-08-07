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
export const RPC_PROVIDER_SYNC_ACTIONS = [
  "created",
  "updated",
  "restored",
  "archived",
  "skipped",
  "failed",
] as const;

export type RpcProviderVendor = (typeof RPC_PROVIDER_VENDORS)[number];
export type RpcProviderSyncStatus = (typeof RPC_PROVIDER_SYNC_STATUSES)[number];
export type ProviderEndpointSyncStatus =
  (typeof PROVIDER_ENDPOINT_SYNC_STATUSES)[number];
export type RpcProviderSyncAction = (typeof RPC_PROVIDER_SYNC_ACTIONS)[number];

const chainSchema = z.enum(CHAINS);
const networkSchema = z.enum(NETWORKS);
const vendorSchema = z.enum(RPC_PROVIDER_VENDORS);
const syncStatusSchema = z.enum(RPC_PROVIDER_SYNC_STATUSES);
const endpointSyncStatusSchema = z.enum(PROVIDER_ENDPOINT_SYNC_STATUSES);
const syncActionSchema = z.enum(RPC_PROVIDER_SYNC_ACTIONS);

const networkPairSchema = z.object({
  chain: chainSchema,
  network: networkSchema,
});

const providerBaseSchema = z.object({
  id: z.string(),
  account_id: z.string(),
  name: z.string(),
  vendor: vendorSchema,
  vendor_label: z.string(),
  enabled: z.boolean(),
  sync_enabled: z.boolean(),
  credential: z.object({ has_secret: z.boolean() }),
  settings: z.record(z.string(), z.unknown()).default({}),
  only_networks: z.array(networkPairSchema).default([]),
  ignore_networks: z.array(networkPairSchema).default([]),
  last_sync_at: z.string().nullable(),
  last_sync_status: syncStatusSchema,
  last_sync_error: z.string().nullable(),
  last_sync_created: z.number().int(),
  last_sync_updated: z.number().int(),
  last_sync_restored: z.number().int(),
  last_sync_archived: z.number().int(),
  last_sync_skipped: z.number().int(),
  version: z.number().int().positive(),
  created_at: z.string(),
  modified_at: z.string(),
});

const providerSchema = providerBaseSchema.transform((provider) => ({
  ...provider,
  last_sync_status_label:
    provider.last_sync_status.charAt(0).toUpperCase() +
    provider.last_sync_status.slice(1),
}));

const providerDetailSchema = providerBaseSchema
  .extend({
    credential: z.object({
      has_secret: z.literal(true),
      secret: z.string(),
    }),
  })
  .transform((provider) => ({
    ...provider,
    last_sync_status_label:
      provider.last_sync_status.charAt(0).toUpperCase() +
      provider.last_sync_status.slice(1),
  }));

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
    enabled: z.boolean(),
    auth: endpointAuthSchema,
    version: z.number().int().positive(),
    created_at: z.string(),
    modified_at: z.string(),
  }),
  sync_status: endpointSyncStatusSchema,
  external_id: z.string(),
  last_seen_at: z.string().nullable(),
  archived_at: z.string().nullable(),
});

const providerEndpointListSchema = z.object({
  page: z.number().int(),
  size: z.number().int(),
  total: z.number().int(),
  max_page: z.number().int(),
  items: z.array(providerEndpointSchema),
});

const syncItemSchema = z.object({
  chain: chainSchema.nullable().optional(),
  network: networkSchema.nullable().optional(),
  action: syncActionSchema,
  endpoint_id: z.string().nullable().optional(),
  external_id: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
});

const syncResultSchema = z
  .object({
    provider_id: z.string(),
    status: syncStatusSchema,
    created: z.number().int(),
    updated: z.number().int(),
    restored: z.number().int(),
    archived: z.number().int(),
    skipped: z.number().int(),
    route_targets_added: z.number().int().nonnegative().default(0),
    route_targets_removed: z.number().int().nonnegative().default(0),
    route_targets_skipped: z.number().int().nonnegative().default(0),
    items: z.array(syncItemSchema),
  })
  .transform((result) => ({
    ...result,
    status_label:
      result.status.charAt(0).toUpperCase() + result.status.slice(1),
    items: result.items.map((item) => ({
      ...item,
      action_label: item.action.charAt(0).toUpperCase() + item.action.slice(1),
    })),
  }));

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
export type RpcProvider = z.infer<typeof providerDetailSchema>;
export type RpcProviderList = z.infer<typeof providerListSchema>;
export type RpcProviderSyncResult = z.infer<typeof syncResultSchema>;
export type RpcProviderSyncItem = RpcProviderSyncResult["items"][number];
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
  only_networks?: RpcProviderNetworkPair[];
  ignore_networks?: RpcProviderNetworkPair[];
};

export type UpdateProviderInput = Partial<{
  name: string;
  enabled: boolean;
  sync_enabled: boolean;
  credential: { secret: string };
  settings: ProviderSettingsInput;
  only_networks: RpcProviderNetworkPair[];
  ignore_networks: RpcProviderNetworkPair[];
}> & { expected_version: number };

export type DeleteProviderInput = {
  delete_unreferenced_endpoints?: boolean;
};

export type ListProvidersParams = {
  vendor?: RpcProviderVendor | RpcProviderVendor[];
  enabled?: boolean;
  sync_enabled?: boolean;
  page?: number;
  size?: number;
};

function buildListParams(
  input: ListProvidersParams,
): Record<string, string | string[]> {
  const params: Record<string, string | string[]> = {};
  if (input.vendor !== undefined) params.vendor = input.vendor;
  if (input.enabled !== undefined) params.enabled = String(input.enabled);
  if (input.sync_enabled !== undefined)
    params.sync_enabled = String(input.sync_enabled);
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

export async function getProvider(id: string): Promise<RpcProvider> {
  const response = await api.get<unknown>(`/v2/providers/${id}`, {
    cache: "no-store",
  });
  return envelope(providerDetailSchema).parse(response).data;
}

export async function createProvider(
  input: CreateProviderInput,
): Promise<RpcProvider> {
  const response = await api.post<unknown>("/v2/providers", input, {
    cache: "no-store",
  });
  return envelope(providerDetailSchema).parse(response).data;
}

export async function updateProvider(
  id: string,
  input: UpdateProviderInput,
): Promise<RpcProvider> {
  const response = await api.patch<unknown>(`/v2/providers/${id}`, input, {
    cache: "no-store",
  });
  return envelope(providerDetailSchema).parse(response).data;
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

export async function syncProvider(id: string): Promise<RpcProviderSyncResult> {
  const response = await api.post<unknown>(`/v2/providers/${id}/sync`);
  return envelope(syncResultSchema).parse(response).data;
}

export async function listProviderEndpoints(
  id: string,
  input: { page?: number; size?: number } = {},
): Promise<ProviderEndpointList> {
  const response = await api.get<unknown>(`/v2/providers/${id}/endpoints`, {
    params: {
      ...(input.page ? { page: String(input.page) } : {}),
      ...(input.size ? { size: String(input.size) } : {}),
    },
    cache: "no-store",
  });
  return envelope(providerEndpointListSchema).parse(response).data;
}
