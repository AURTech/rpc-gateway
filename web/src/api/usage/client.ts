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

const usageWindowSchema = usageMetricsSchema.extend({
  time_range: usageRangeSchema,
  start_at: z.string(),
  end_at: z.string(),
  data_through: z.string(),
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

const envelope = <T extends z.ZodType>(data: T) =>
  z.object({ msg: z.string(), data });

export type RpcUsageRange = z.infer<typeof usageRangeSchema>;
export type RpcUsageMethodRank = z.infer<typeof usageMethodRankSchema>;
export type RpcUsageMetrics = z.infer<typeof usageMetricsSchema>;
export type RpcUsageWindow = z.infer<typeof usageWindowSchema>;
export type RpcUsageMetricsPoint = z.infer<typeof usageMetricsPointSchema>;
export type RpcUsageSeries = z.infer<typeof usageSeriesSchema>;
export type RpcUsageByMethod = z.infer<typeof usageByMethodSchema>;
export type RpcUsageByNetwork = z.infer<typeof usageByNetworkSchema>;

export type UsageParams = {
  range?: RpcUsageRange;
  app_id?: string;
  gateway_id?: string;
  chain?: z.infer<typeof rpcChainSchema>;
  network?: z.infer<typeof rpcNetworkSchema>;
};

export type UsageGroupedParams = UsageParams & { limit?: number };
export type UsageMethodParams = UsageGroupedParams & {
  rank_by?: RpcUsageMethodRank;
};
export type UsageNetworkParams = UsageGroupedParams;

function toParams(input: UsageParams): Record<string, string> {
  const out: Record<string, string> = {};
  if (input.range) out.time_range = input.range;
  if (input.app_id) out.app_id = input.app_id;
  if (input.gateway_id) out.gateway_id = input.gateway_id;
  if (input.chain) out.chain = input.chain;
  if (input.network) out.network = input.network;
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
