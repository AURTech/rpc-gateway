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
export const ENDPOINT_HEALTH_FAILURES = [
  "connection",
  "timeout",
  "auth",
  "server",
  "protocol",
  "config",
] as const;
export const ENDPOINT_AUTH_TYPES = [
  "none",
  "bearer",
  "header_api_key",
  "query_api_key",
  "path_api_key",
] as const;
export type EndpointOriginType = (typeof ENDPOINT_ORIGIN_TYPES)[number];
export type EndpointProtocol = (typeof ENDPOINT_PROTOCOLS)[number];
export type EndpointAuthType = (typeof ENDPOINT_AUTH_TYPES)[number];

const originTypeSchema = z.enum(ENDPOINT_ORIGIN_TYPES);
const protocolSchema = z.enum(ENDPOINT_PROTOCOLS);
const chainSchema = z.enum(CHAINS);
const networkSchema = z.enum(NETWORKS);

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
  enabled: z.boolean(),
  auth: endpointAuthSchema,
  version: z.number().int().positive(),
  created_at: z.string(),
  modified_at: z.string(),
});

const endpointDetailSchema = endpointSchema.extend({
  configured_url: z.string(),
  auth: endpointAuthDetailSchema,
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
  referenced_ids: z.array(z.string()),
});

const endpointHealthSchema = z.object({
  status: z.enum(ENDPOINT_HEALTH_STATUSES),
  error_rate: z.number().min(0).max(1),
  latency_ms: z.number().nonnegative().nullable(),
  samples: z.number().int().nonnegative(),
  last_observed_at: z.string(),
  last_success_at: z.string().nullable(),
  last_failure_at: z.string().nullable(),
  last_failure: z.enum(ENDPOINT_HEALTH_FAILURES).nullable(),
});

const endpointHealthCheckSchema = z.object({
  endpoint_id: z.string(),
  checked_at: z.string(),
  success: z.boolean(),
  limited: z.boolean(),
  latency_ms: z.number().nonnegative().nullable(),
  failure: z.enum(ENDPOINT_HEALTH_FAILURES).nullable(),
  health: endpointHealthSchema,
});

const endpointAuditActionSchema = z.enum(["created", "updated", "deleted"]);

const endpointAuditEventSchema = z.object({
  id: z.string(),
  endpoint_id: z.string(),
  account_id: z.string(),
  actor_id: z.string(),
  action: endpointAuditActionSchema,
  previous_version: z.number().int().positive().nullable(),
  new_version: z.number().int().positive(),
  changed_fields: z.array(z.string()),
  created_at: z.string(),
});

const endpointAuditEventListSchema = z.object({
  page: z.number().int(),
  size: z.number().int(),
  total: z.number().int(),
  max_page: z.number().int(),
  items: z.array(endpointAuditEventSchema),
});

const envelope = <T extends z.ZodType>(data: T) =>
  z.object({ msg: z.string(), data });

export type Endpoint = z.infer<typeof endpointSchema>;
export type EndpointAuth = z.infer<typeof endpointAuthSchema>;
export type EndpointDetail = z.infer<typeof endpointDetailSchema>;
export type EndpointList = z.infer<typeof endpointListSchema>;
export type EndpointAuditEvent = z.infer<typeof endpointAuditEventSchema>;
export type EndpointAuditEventList = z.infer<
  typeof endpointAuditEventListSchema
>;
export type EndpointDeleteResult = z.infer<typeof endpointDeleteResultSchema>;
export type BulkDeleteEndpointResult = z.infer<
  typeof bulkDeleteEndpointResultSchema
>;
export type EndpointHealth = z.infer<typeof endpointHealthSchema>;
export type EndpointHealthCheck = z.infer<typeof endpointHealthCheckSchema>;

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

export async function listEndpointAuditEvents(
  id: string,
  page = 1,
  size = 20,
): Promise<EndpointAuditEventList> {
  const response = await api.get<unknown>(`/v2/endpoints/${id}/audit-events`, {
    params: { page: String(page), size: String(size) },
  });
  return envelope(endpointAuditEventListSchema).parse(response).data;
}
