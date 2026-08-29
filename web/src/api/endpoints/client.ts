import { z } from "zod/v4";

import { api } from "@/api/client";
import { CHAINS, type Chain, NETWORKS, type Network } from "@/lib/blockchain";

export const ENDPOINT_ORIGIN_TYPES = ["manual", "provider"] as const;
export const ENDPOINT_PROTOCOLS = ["jsonrpc", "http_api"] as const;
export const ENDPOINT_HEALTH_STATUSES = [
  "unknown",
  "healthy",
  "unhealthy",
] as const;
export const ENDPOINT_ROUTE_TYPES = [
  "jsonrpc_default",
  "jsonrpc_method",
  "http_api",
] as const;
export const ENDPOINT_ROUTE_STRATEGY_TYPES = [
  "priority_failover",
  "load_balance",
] as const;
export type EndpointOriginType = (typeof ENDPOINT_ORIGIN_TYPES)[number];
export type EndpointProtocol = (typeof ENDPOINT_PROTOCOLS)[number];

const originTypeSchema = z.enum(ENDPOINT_ORIGIN_TYPES);
const protocolSchema = z.enum(ENDPOINT_PROTOCOLS);
const chainSchema = z.enum(CHAINS);
const networkSchema = z.enum(NETWORKS);
const endpointHealthSchema = z.object({
  status: z.enum(ENDPOINT_HEALTH_STATUSES),
  last_observed_at: z.string(),
});
const endpointHealthCheckSchema = endpointHealthSchema.extend({
  status: z.enum(["healthy", "unhealthy"]),
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

const endpointAuthDetailSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("none"), has_secret: z.literal(false) }),
  z.object({
    type: z.literal("bearer"),
    has_secret: z.literal(true),
    secret: z.string(),
  }),
  z.object({
    type: z.literal("header_api_key"),
    header_name: z.string(),
    has_secret: z.literal(true),
    secret: z.string(),
  }),
  z.object({
    type: z.literal("query_api_key"),
    query_param: z.string(),
    has_secret: z.literal(true),
    secret: z.string(),
  }),
  z.object({
    type: z.literal("path_api_key"),
    has_secret: z.literal(true),
    secret: z.string(),
  }),
]);

const endpointSchema = z.object({
  id: z.string(),
  account_id: z.string(),
  name: z.string(),
  origin_type: originTypeSchema,
  provider: z
    .object({
      id: z.string(),
      name: z.string(),
      vendor: z.enum([
        "alchemy",
        "quicknode",
        "chainstack",
        "drpc",
        "tenderly",
      ]),
      vendor_label: z.string(),
    })
    .nullable(),
  provider_external_id: z.string().nullable(),
  provider_sync_status: z.enum(["available", "missing"]).nullable(),
  provider_last_seen_at: z.string().nullable(),
  chain: chainSchema,
  network: networkSchema,
  protocol: protocolSchema,
  url: z.string(),
  effective_url: z.string().nullable(),
  enabled: z.boolean(),
  auth: endpointAuthSchema,
  health: endpointHealthSchema.nullable(),
  version: z.number().int().positive(),
  created_at: z.string(),
  modified_at: z.string(),
});

const endpointDetailSchema = endpointSchema.extend({
  auth: z.union([endpointAuthDetailSchema, endpointAuthSchema]),
});

const endpointListSchema = z.object({
  page: z.number().int(),
  size: z.number().int(),
  total: z.number().int(),
  max_page: z.number().int(),
  items: z.array(endpointSchema),
});

const endpointDeleteResultSchema = z.object({
  id: z.string(),
  version: z.number().int().positive(),
  deleted: z.boolean(),
});

const bulkDeleteEndpointResultSchema = z.object({
  total: z.number().int().nonnegative(),
  deleted: z.array(endpointDeleteResultSchema),
});

const endpointRouteBindingSchema = z.object({
  route_type: z.enum(ENDPOINT_ROUTE_TYPES),
  route_id: z.string(),
  route_version: z.number().int().positive(),
  strategy_type: z.enum(ENDPOINT_ROUTE_STRATEGY_TYPES),
  methods: z.array(z.string()),
  target_count: z.number().int().positive(),
  gateway: z.object({
    id: z.string(),
    app_id: z.string(),
    name: z.string(),
  }),
});

const endpointRouteBindingListSchema = z.object({
  total: z.number().int().nonnegative(),
  items: z.array(endpointRouteBindingSchema),
});

const endpointRouteBindingDeleteResultSchema = z.object({
  endpoint_id: z.string(),
  route_type: z.enum(ENDPOINT_ROUTE_TYPES),
  route_id: z.string(),
  route_deleted: z.boolean(),
  route_version: z.number().int().positive().nullable(),
});

const envelope = <T extends z.ZodType>(data: T) =>
  z.object({ msg: z.string(), data });

export type Endpoint = z.infer<typeof endpointSchema>;
export type EndpointDetail = z.infer<typeof endpointDetailSchema>;
export type EndpointList = z.infer<typeof endpointListSchema>;
export type EndpointDeleteResult = z.infer<typeof endpointDeleteResultSchema>;
export type BulkDeleteEndpointResult = z.infer<
  typeof bulkDeleteEndpointResultSchema
>;
export type EndpointHealth = z.infer<typeof endpointHealthSchema>;
export type EndpointHealthCheck = z.infer<typeof endpointHealthCheckSchema>;
export type EndpointRouteBinding = z.infer<typeof endpointRouteBindingSchema>;
export type EndpointRouteBindingList = z.infer<
  typeof endpointRouteBindingListSchema
>;
export type EndpointRouteBindingDeleteResult = z.infer<
  typeof endpointRouteBindingDeleteResultSchema
>;

export type EndpointCreateAuth =
  | { type: "none" }
  | { type: "bearer"; secret: string }
  | { type: "header_api_key"; header_name: string; secret: string }
  | { type: "query_api_key"; query_param: string; secret: string }
  | { type: "path_api_key"; secret: string };

export type EndpointUpdateAuth =
  | { type: "none" }
  | { type: "bearer"; secret?: string }
  | { type: "header_api_key"; header_name?: string; secret?: string }
  | { type: "query_api_key"; query_param?: string; secret?: string }
  | { type: "path_api_key"; secret?: string };

export type CreateEndpointInput = {
  name: string;
  chain: Chain;
  network: Network;
  protocol: EndpointProtocol;
  url: string;
  enabled: boolean;
  auth: EndpointCreateAuth;
};

export type UpdateEndpointInput = {
  expected_version: number;
  name?: string;
  url?: string;
  enabled?: boolean;
  auth?: EndpointUpdateAuth;
};

export type ListEndpointsParams = {
  q?: string;
  chain?: readonly Chain[];
  network?: readonly Network[];
  protocol?: EndpointProtocol;
  enabled?: boolean;
  origin_type?: EndpointOriginType;
  provider_id?: string;
  page?: number;
  size?: number;
};

function buildListParams(
  input: ListEndpointsParams,
): Record<string, string | string[]> {
  const params: Record<string, string | string[]> = {};
  if (input.q) params.q = input.q;
  if (input.chain?.length) params.chain = [...input.chain];
  if (input.network?.length) params.network = [...input.network];
  if (input.protocol) params.protocol = input.protocol;
  if (input.enabled !== undefined) params.enabled = String(input.enabled);
  if (input.origin_type) params.origin_type = input.origin_type;
  if (input.provider_id) params.provider_id = input.provider_id;
  if (input.page) params.page = String(input.page);
  if (input.size) params.size = String(input.size);
  return params;
}

export async function listEndpoints(
  input: ListEndpointsParams = {},
): Promise<EndpointList> {
  const response = await api.get<unknown>("/v2/endpoints", {
    params: buildListParams(input),
    cache: "no-store",
  });
  return envelope(endpointListSchema).parse(response).data;
}

export async function getEndpoint(id: string): Promise<EndpointDetail> {
  const response = await api.get<unknown>(`/v2/endpoints/${id}`, {
    cache: "no-store",
  });
  return envelope(endpointDetailSchema).parse(response).data;
}

export async function createEndpoint(
  input: CreateEndpointInput,
): Promise<EndpointDetail> {
  const response = await api.post<unknown>("/v2/endpoints", input, {
    cache: "no-store",
  });
  return envelope(endpointDetailSchema).parse(response).data;
}

export async function updateEndpoint(
  id: string,
  input: UpdateEndpointInput,
): Promise<EndpointDetail> {
  const response = await api.patch<unknown>(`/v2/endpoints/${id}`, input, {
    cache: "no-store",
  });
  return envelope(endpointDetailSchema).parse(response).data;
}

export async function deleteEndpoint(
  id: string,
): Promise<EndpointDeleteResult> {
  const response = await api.delete<unknown>(`/v2/endpoints/${id}`);
  return envelope(endpointDeleteResultSchema).parse(response).data;
}

export async function bulkDeleteEndpoints(
  endpointIds: readonly string[],
): Promise<BulkDeleteEndpointResult> {
  const response = await api.post<unknown>("/v2/endpoints/bulk-delete", {
    endpoint_ids: endpointIds,
  });
  return envelope(bulkDeleteEndpointResultSchema).parse(response).data;
}

export async function checkEndpointHealth(
  id: string,
): Promise<EndpointHealthCheck> {
  const response = await api.post<unknown>(
    `/v2/endpoints/${id}/health-checks`,
    undefined,
    { cache: "no-store" },
  );
  return envelope(endpointHealthCheckSchema).parse(response).data;
}

export async function listEndpointRouteBindings(
  id: string,
): Promise<EndpointRouteBindingList> {
  const response = await api.get<unknown>(
    `/v2/endpoints/${id}/route-bindings`,
    { cache: "no-store" },
  );
  return envelope(endpointRouteBindingListSchema).parse(response).data;
}

export async function deleteEndpointRouteBinding(
  endpointId: string,
  binding: Pick<
    EndpointRouteBinding,
    "route_type" | "route_id" | "route_version"
  >,
): Promise<EndpointRouteBindingDeleteResult> {
  const response = await api.delete<unknown>(
    `/v2/endpoints/${endpointId}/route-bindings/${binding.route_type}/${binding.route_id}`,
    { params: { expected_version: String(binding.route_version) } },
  );
  return envelope(endpointRouteBindingDeleteResultSchema).parse(response).data;
}
