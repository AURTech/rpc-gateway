import {
  keepPreviousData,
  type QueryKey,
  useQuery,
} from "@tanstack/react-query";

import {
  getUsageByMethod,
  getUsageByNetwork,
  getUsageSeries,
  getUsageSummary,
  type RpcUsageByMethod,
  type RpcUsageByNetwork,
  type RpcUsageSeries,
  type RpcUsageWindow,
  type UsageMethodParams,
  type UsageNetworkParams,
  type UsageParams,
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
};

const SHARED = {
  staleTime: 30_000,
  placeholderData: keepPreviousData,
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
