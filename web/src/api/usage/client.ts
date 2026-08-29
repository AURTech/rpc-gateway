import { z } from "zod/v4";

import { api } from "@/api/client";
import { RPC_CHAINS, RPC_NETWORKS } from "@/lib/rpc-chain";

const rpcChainSchema = z.enum(RPC_CHAINS);
const rpcNetworkSchema = z.enum(RPC_NETWORKS);
export const RPC_USAGE_RANGES = [
  "hourly",
  "daily",
  "weekly",
  "monthly",
] as const;
const usageRangeSchema = z.enum(RPC_USAGE_RANGES);
const usageGranularitySchema = z.enum(["five_minute", "hourly", "daily"]);
const usageMethodRankSchema = z.enum([
  "total_requests",
  "cache_eligible_requests",
]);

const usageMetricsSchema = z.object({
  total_requests: z.number().int(),
  successful_requests: z.number().int(),
  failed_requests: z.number().int(),
  success_rate: z.number(),
  total_duration_ms: z.number().int(),
  avg_duration_ms: z.number(),
  total_request_bytes: z.number().int(),
  total_response_bytes: z.number().int(),
  total_traffic_bytes: z.number().int(),
  cache_eligible_requests: z.number().int(),
  cache_hit_requests: z.number().int(),
  cache_hit_rate: z.number(),
});

// The comparison window the server returns for `compare=true`: the same span
// shifted back so it ends where the reported window starts.
const usagePreviousWindowSchema = usageMetricsSchema.extend({
  start_at: z.string(),
  end_at: z.string(),
});

const usageWindowSchema = usageMetricsSchema.extend({
  time_range: usageRangeSchema,
  start_at: z.string(),
  end_at: z.string(),
  data_through: z.string(),
  previous: usagePreviousWindowSchema.nullish(),
});

const usageMetricsPointSchema = usageMetricsSchema.extend({
  bucket_start: z.string(),
});

const usageSeriesSchema = z.object({
  time_range: usageRangeSchema,
  granularity: usageGranularitySchema,
  data_through: z.string(),
  items: z.array(usageMetricsPointSchema),
});

const usageMethodPointSchema = z.object({
  bucket_start: z.string(),
  total_requests: z.number().int(),
  cache_eligible_requests: z.number().int(),
  cache_hit_requests: z.number().int(),
  cache_hit_rate: z.number(),
});

const usageByMethodSchema = z.object({
  time_range: usageRangeSchema,
  granularity: usageGranularitySchema,
  data_through: z.string(),
  items: z.array(
    z.object({
      method: z.string(),
      points: z.array(usageMethodPointSchema),
    }),
  ),
});

const usageNetworkPointSchema = z.object({
  bucket_start: z.string(),
  total_requests: z.number().int(),
  total_duration_ms: z.number().int(),
  avg_duration_ms: z.number(),
  cache_eligible_requests: z.number().int(),
  cache_hit_requests: z.number().int(),
  cache_hit_rate: z.number(),
});

const usageByNetworkSchema = z.object({
  time_range: usageRangeSchema,
  granularity: usageGranularitySchema,
  data_through: z.string(),
  items: z.array(
    z.object({
      chain: rpcChainSchema,
      chain_label: z.string(),
      network: rpcNetworkSchema,
      network_label: z.string(),
      points: z.array(usageNetworkPointSchema),
    }),
  ),
});

const usageEndpointPointSchema = z.object({
  bucket_start: z.string(),
  total_attempts: z.number().int().nonnegative(),
  first_attempts: z.number().int().nonnegative(),
  retry_attempts: z.number().int().nonnegative(),
  unclassified_attempts: z.number().int().nonnegative(),
});

const usageByEndpointSchema = z.object({
  time_range: usageRangeSchema,
  granularity: usageGranularitySchema,
  start_at: z.string(),
  end_at: z.string(),
  data_through: z.string(),
  classification_coverage_start_at: z.string().nullable(),
  classification_coverage_complete: z.boolean(),
  total_attempts: z.number().int().nonnegative(),
  first_attempts: z.number().int().nonnegative(),
  retry_attempts: z.number().int().nonnegative(),
  unclassified_attempts: z.number().int().nonnegative(),
  observed_endpoint_count: z.number().int().nonnegative(),
  items: z.array(
    z.object({
      endpoint_id: z.string(),
      name: z.string(),
      chain: rpcChainSchema,
      network: rpcNetworkSchema,
      protocol: z.enum(["jsonrpc", "http_api"]).nullable(),
      historical: z.boolean(),
      total_attempts: z.number().int().nonnegative(),
      first_attempts: z.number().int().nonnegative(),
      retry_attempts: z.number().int().nonnegative(),
      unclassified_attempts: z.number().int().nonnegative(),
      points: z.array(usageEndpointPointSchema),
    }),
  ),
  other_total_attempts: z.number().int().nonnegative(),
  other_first_attempts: z.number().int().nonnegative(),
  other_retry_attempts: z.number().int().nonnegative(),
  other_unclassified_attempts: z.number().int().nonnegative(),
  other_points: z.array(usageEndpointPointSchema),
});

const usageRouteMetricsSchema = z.object({
  routed_requests: z.number().int().nonnegative(),
  successful_requests: z.number().int().nonnegative(),
  failed_requests: z.number().int().nonnegative(),
  success_rate: z.number(),
  total_duration_ms: z.number().int().nonnegative(),
  avg_duration_ms: z.number().nonnegative(),
  total_attempts: z.number().int().nonnegative(),
  avg_attempts: z.number().nonnegative(),
  multi_attempt_requests: z.number().int().nonnegative(),
  multi_attempt_rate: z.number(),
  exhausted_requests: z.number().int().nonnegative(),
  exhausted_rate: z.number(),
});

const usageRouteItemSchema = usageRouteMetricsSchema.extend({
  route_id: z.string(),
  gateway_id: z.string(),
  chain: rpcChainSchema,
  network: rpcNetworkSchema,
  points: z.array(
    usageRouteMetricsSchema.extend({
      bucket_start: z.string(),
    }),
  ),
});

const usageByRouteSchema = z.object({
  time_range: usageRangeSchema,
  granularity: usageGranularitySchema,
  start_at: z.string(),
  end_at: z.string(),
  data_through: z.string(),
  coverage_start_at: z.string().nullable(),
  coverage_complete: z.boolean(),
  items: z.array(usageRouteItemSchema),
});

const envelope = <T extends z.ZodType>(data: T) =>
  z.object({ msg: z.string(), data });

export type RpcUsageRange = z.infer<typeof usageRangeSchema>;
export type RpcUsageMethodRank = z.infer<typeof usageMethodRankSchema>;
export type RpcUsagePreviousWindow = z.infer<typeof usagePreviousWindowSchema>;
export type RpcUsageWindow = z.infer<typeof usageWindowSchema>;
export type RpcUsageMetricsPoint = z.infer<typeof usageMetricsPointSchema>;
export type RpcUsageSeries = z.infer<typeof usageSeriesSchema>;
export type RpcUsageByMethod = z.infer<typeof usageByMethodSchema>;
export type RpcUsageByNetwork = z.infer<typeof usageByNetworkSchema>;
export type RpcUsageByEndpoint = z.infer<typeof usageByEndpointSchema>;
export type RpcUsageByRoute = z.infer<typeof usageByRouteSchema>;
export type RpcUsageRouteItem = z.infer<typeof usageRouteItemSchema>;

export type UsageParams = {
  range?: RpcUsageRange;
  app_id?: string;
  gateway_id?: string;
  chain?: z.infer<typeof rpcChainSchema>;
  network?: z.infer<typeof rpcNetworkSchema>;
  // Only `/v2/usage/summary` reads this; it asks the server for the preceding
  // window alongside the reported one.
  compare?: boolean;
};

export type UsageGroupedParams = UsageParams & { limit?: number };
export type UsageMethodParams = UsageGroupedParams & {
  rank_by?: RpcUsageMethodRank;
};
export type UsageNetworkParams = UsageGroupedParams;
export type UsageRouteParams = {
  range?: RpcUsageRange;
  app_id: string;
  gateway_id?: string;
  limit?: number;
};
export type UsageEndpointParams = {
  range?: RpcUsageRange;
  app_id?: string;
  gateway_id?: string;
  route_id?: string;
  limit?: number;
};

function toParams(input: UsageParams): Record<string, string> {
  const out: Record<string, string> = {};
  if (input.range) out.time_range = input.range;
  if (input.app_id) out.app_id = input.app_id;
  if (input.gateway_id) out.gateway_id = input.gateway_id;
  if (input.chain) out.chain = input.chain;
  if (input.network) out.network = input.network;
  if (input.compare) out.compare = "true";
  return out;
}

function toGroupedParams(input: UsageGroupedParams): Record<string, string> {
  const out = toParams(input);
  if (input.limit != null) out.limit = String(input.limit);
  return out;
}

function toMethodParams(input: UsageMethodParams): Record<string, string> {
  const out = toGroupedParams(input);
  if (input.rank_by) out.rank_by = input.rank_by;
  return out;
}

export async function getUsageSummary(
  input: UsageParams = {},
): Promise<RpcUsageWindow> {
  const response = await api.get<unknown>("/v2/usage/summary", {
    params: toParams(input),
  });
  return envelope(usageWindowSchema).parse(response).data;
}

export async function getUsageSeries(
  input: UsageParams = {},
): Promise<RpcUsageSeries> {
  const response = await api.get<unknown>("/v2/usage/series", {
    params: toParams(input),
  });
  return envelope(usageSeriesSchema).parse(response).data;
}

export async function getUsageByMethod(
  input: UsageMethodParams = {},
): Promise<RpcUsageByMethod> {
  const response = await api.get<unknown>("/v2/usage/methods", {
    params: toMethodParams(input),
  });
  return envelope(usageByMethodSchema).parse(response).data;
}

export async function getUsageByNetwork(
  input: UsageNetworkParams = {},
): Promise<RpcUsageByNetwork> {
  const response = await api.get<unknown>("/v2/usage/networks", {
    params: toGroupedParams(input),
  });
  return envelope(usageByNetworkSchema).parse(response).data;
}

export async function getUsageByRoute(
  input: UsageRouteParams,
): Promise<RpcUsageByRoute> {
  const response = await api.get<unknown>("/v2/usage/routes", {
    params: toGroupedParams(input),
  });
  return envelope(usageByRouteSchema).parse(response).data;
}

export async function getUsageByEndpoint(
  input: UsageEndpointParams,
): Promise<RpcUsageByEndpoint> {
  const params: Record<string, string> = {};
  if (input.range) params.time_range = input.range;
  if (input.app_id) params.app_id = input.app_id;
  if (input.gateway_id) params.gateway_id = input.gateway_id;
  if (input.route_id) params.route_id = input.route_id;
  if (input.limit != null) params.limit = String(input.limit);
  const response = await api.get<unknown>("/v2/usage/endpoints", { params });
  return envelope(usageByEndpointSchema).parse(response).data;
}
