import {
  keepPreviousData,
  type QueryKey,
  useQuery,
} from "@tanstack/react-query";

import {
  getUsageByEndpoint,
  getUsageByMethod,
  getUsageByNetwork,
  getUsageByRoute,
  getUsageSeries,
  getUsageSummary,
  type RpcUsageByEndpoint,
  type RpcUsageByMethod,
  type RpcUsageByNetwork,
  type RpcUsageByRoute,
  type RpcUsageSeries,
  type RpcUsageWindow,
  type UsageEndpointParams,
  type UsageMethodParams,
  type UsageNetworkParams,
  type UsageParams,
  type UsageRouteParams,
} from "@/api/usage/client";

const root = ["usage"] as const;

export const usageKeys = {
  all: root,
  summary: (params: UsageParams) => [...root, "summary", params] as const,
  series: (params: UsageParams) => [...root, "series", params] as const,
  byMethod: (params: UsageMethodParams) =>
    [...root, "byMethod", params] as const,
  byNetwork: (params: UsageNetworkParams) =>
    [...root, "byNetwork", params] as const,
  byRoute: (params: UsageRouteParams) => [...root, "byRoute", params] as const,
  byEndpoint: (params: UsageEndpointParams) =>
    [...root, "byEndpoint", params] as const,
};

const SHARED = {
  staleTime: 30_000,
  placeholderData: keepPreviousData,
} as const;

const SCOPE_BOUND = {
  staleTime: 30_000,
} as const;

export function useUsageSummaryQuery(params: UsageParams = {}) {
  return useQuery<RpcUsageWindow>({
    queryKey: usageKeys.summary(params) as unknown as QueryKey,
    queryFn: () => getUsageSummary(params),
    ...SHARED,
  });
}

export function useUsageSeriesQuery(params: UsageParams = {}) {
  return useQuery<RpcUsageSeries>({
    queryKey: usageKeys.series(params) as unknown as QueryKey,
    queryFn: () => getUsageSeries(params),
    ...SHARED,
  });
}

export function useUsageByMethodQuery(params: UsageMethodParams = {}) {
  return useQuery<RpcUsageByMethod>({
    queryKey: usageKeys.byMethod(params) as unknown as QueryKey,
    queryFn: () => getUsageByMethod(params),
    ...SHARED,
  });
}

export function useUsageByNetworkQuery(params: UsageNetworkParams = {}) {
  return useQuery<RpcUsageByNetwork>({
    queryKey: usageKeys.byNetwork(params) as unknown as QueryKey,
    queryFn: () => getUsageByNetwork(params),
    ...SHARED,
  });
}

export function useUsageByRouteQuery(
  params: UsageRouteParams,
  options: { enabled?: boolean } = {},
) {
  return useQuery<RpcUsageByRoute>({
    queryKey: usageKeys.byRoute(params) as unknown as QueryKey,
    queryFn: () => getUsageByRoute(params),
    enabled: options.enabled,
    ...SCOPE_BOUND,
  });
}

export function useUsageByEndpointQuery(
  params: UsageEndpointParams,
  options: { enabled?: boolean } = {},
) {
  return useQuery<RpcUsageByEndpoint>({
    queryKey: usageKeys.byEndpoint(params) as unknown as QueryKey,
    queryFn: () => getUsageByEndpoint(params),
    enabled: options.enabled,
    ...SCOPE_BOUND,
  });
}
