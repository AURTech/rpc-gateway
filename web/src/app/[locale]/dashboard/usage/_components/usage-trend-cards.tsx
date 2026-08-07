"use client";

import { useTranslations } from "next-intl";
import { useDeferredValue, useMemo, useState } from "react";

import type { RpcUsageRange } from "@/api/usage/client";
import {
  bytesFormat,
  cacheByMethodSeries,
  cacheSeries,
  durationFormat,
  latencySeries,
  methodSeries,
  networkSeries,
  overallSeries,
  percentFormat,
  TrendChartCard,
  trafficSeries,
} from "@/components/dashboard/usage-trend-chart";
import {
  useUsageByMethodQuery,
  useUsageByNetworkQuery,
  useUsageSeriesQuery,
} from "@/hooks/use-usage";

import {
  DEFAULT_USAGE_RANGE,
  type UsageChartFilters,
  UsageFilterToolchain,
  UsageRangeSelect,
  type UsageScope,
} from "./usage-filter-bar";

export type { UsageScope };

const EMPTY_SCOPE: UsageScope = {};
const CACHE_METHOD_LIMIT = 8;
const NETWORK_METRIC_LIMIT = 100;

type UsageTrendCardProps = {
  scope?: UsageScope;
  filters?: UsageChartFilters;
  onFiltersChange?: (next: UsageChartFilters) => void;
};

// Cards without `filters` keep local range state. Controlled cards either show
// their own filter toolchain when `onFiltersChange` is supplied, or omit the
// card action when a parent toolbar owns the filters for every chart.
function useCardFilters({
  scope = EMPTY_SCOPE,
  filters,
  onFiltersChange,
}: UsageTrendCardProps) {
  const [range, setRange] = useState<RpcUsageRange>(DEFAULT_USAGE_RANGE);
  const localFilters = useMemo<UsageChartFilters>(() => ({ range }), [range]);
  const activeFilters = filters ?? localFilters;
  const deferredScope = useDeferredValue(scope);
  const deferredFilters = useDeferredValue(activeFilters);
  const queryFilters = useMemo(
    () => ({
      ...deferredScope,
      ...(deferredFilters.chain ? { chain: deferredFilters.chain } : {}),
      ...(deferredFilters.network ? { network: deferredFilters.network } : {}),
      range: deferredFilters.range,
    }),
    [deferredScope, deferredFilters],
  );

  const action = filters ? (
    onFiltersChange ? (
      <UsageFilterToolchain value={filters} onChange={onFiltersChange} />
    ) : null
  ) : (
    <UsageRangeSelect value={range} onChange={setRange} />
  );

  return { range: queryFilters.range, filters: queryFilters, action };
}

export function MethodTrendCard(props: UsageTrendCardProps) {
  const t = useTranslations("dashboard.usage");
  const { range, filters, action } = useCardFilters(props);
  const query = useUsageByMethodQuery(filters);

  return (
    <TrendChartCard
      title={t("methods.title")}
      subhead={t("methods.subhead")}
      isPending={query.isPending}
      isFetching={query.isFetching}
      isError={query.isError}
      onRetry={() => query.refetch()}
      series={methodSeries(query.data)}
      kind="area"
      emptyLabel={t("methods.empty")}
      errorLabel={t("error.title")}
      retryLabel={t("error.retry")}
      range={range}
      dataThrough={query.data?.data_through}
      dataThroughLabel={t("dataThrough")}
      action={action}
    />
  );
}

// Overall request volume over time, split success (green) vs. failure (red).
// Backed by `/v2/usage/series`.
export function OverallTrendCard(props: UsageTrendCardProps) {
  const t = useTranslations("dashboard.usage");
  const { range, filters, action } = useCardFilters(props);
  const query = useUsageSeriesQuery(filters);

  return (
    <TrendChartCard
      title={t("overall.title")}
      subhead={t("overall.subhead")}
      isPending={query.isPending}
      isFetching={query.isFetching}
      isError={query.isError}
      onRetry={() => query.refetch()}
      series={overallSeries(query.data, {
        success: t("overall.success"),
        failure: t("overall.failure"),
      })}
      kind="area"
      emptyLabel={t("overall.empty")}
      errorLabel={t("error.title")}
      retryLabel={t("error.retry")}
      range={range}
      dataThrough={query.data?.data_through}
      dataThroughLabel={t("dataThrough")}
      action={action}
    />
  );
}

export function NetworkTrendCard(props: UsageTrendCardProps) {
  const t = useTranslations("dashboard.usage");
  const { range, filters, action } = useCardFilters(props);
  const query = useUsageByNetworkQuery(filters);

  return (
    <TrendChartCard
      title={t("network.title")}
      subhead={t("network.subhead")}
      isPending={query.isPending}
      isFetching={query.isFetching}
      isError={query.isError}
      onRetry={() => query.refetch()}
      series={networkSeries(query.data)}
      kind="area"
      emptyLabel={t("network.empty")}
      errorLabel={t("error.title")}
      retryLabel={t("error.retry")}
      range={range}
      dataThrough={query.data?.data_through}
      dataThroughLabel={t("dataThrough")}
      action={action}
    />
  );
}

export function CacheTrendCard(props: UsageTrendCardProps) {
  const t = useTranslations("dashboard.usage");
  const { range, filters, action } = useCardFilters(props);
  const query = useUsageByNetworkQuery({
    ...filters,
    limit: NETWORK_METRIC_LIMIT,
  });

  return (
    <TrendChartCard
      title={t("cache.title")}
      subhead={t("cache.subhead")}
      isPending={query.isPending}
      isFetching={query.isFetching}
      isError={query.isError}
      onRetry={() => query.refetch()}
      series={cacheSeries(query.data)}
      kind="line"
      format={percentFormat}
      emptyLabel={t("cache.empty")}
      errorLabel={t("error.title")}
      retryLabel={t("error.retry")}
      range={range}
      dataThrough={query.data?.data_through}
      dataThroughLabel={t("dataThrough")}
      action={action}
    />
  );
}

export function TrafficTrendCard(props: UsageTrendCardProps) {
  const t = useTranslations("dashboard.usage");
  const { range, filters, action } = useCardFilters(props);
  const query = useUsageSeriesQuery(filters);

  return (
    <TrendChartCard
      title={t("traffic.title")}
      subhead={t("traffic.subhead")}
      isPending={query.isPending}
      isFetching={query.isFetching}
      isError={query.isError}
      onRetry={() => query.refetch()}
      series={trafficSeries(query.data, {
        request: t("traffic.upload"),
        response: t("traffic.download"),
      })}
      kind="area-stacked"
      format={bytesFormat}
      emptyLabel={t("traffic.empty")}
      errorLabel={t("error.title")}
      retryLabel={t("error.retry")}
      range={range}
      dataThrough={query.data?.data_through}
      dataThroughLabel={t("dataThrough")}
      action={action}
    />
  );
}

export function CacheByMethodTrendCard(props: UsageTrendCardProps) {
  const t = useTranslations("dashboard.usage");
  const { range, filters, action } = useCardFilters(props);
  const query = useUsageByMethodQuery({
    ...filters,
    rank_by: "cache_eligible_requests",
    limit: CACHE_METHOD_LIMIT,
  });

  return (
    <TrendChartCard
      title={t("cacheByMethod.title")}
      subhead={t("cacheByMethod.subhead")}
      isPending={query.isPending}
      isFetching={query.isFetching}
      isError={query.isError}
      onRetry={() => query.refetch()}
      series={cacheByMethodSeries(query.data)}
      kind="line"
      format={percentFormat}
      emptyLabel={t("cacheByMethod.empty")}
      errorLabel={t("error.title")}
      retryLabel={t("error.retry")}
      range={range}
      dataThrough={query.data?.data_through}
      dataThroughLabel={t("dataThrough")}
      action={action}
    />
  );
}

export function LatencyTrendCard(props: UsageTrendCardProps) {
  const t = useTranslations("dashboard.usage");
  const { range, filters, action } = useCardFilters(props);
  const query = useUsageByNetworkQuery({
    ...filters,
    limit: NETWORK_METRIC_LIMIT,
  });

  return (
    <TrendChartCard
      title={t("latency.title")}
      subhead={t("latency.subhead")}
      isPending={query.isPending}
      isFetching={query.isFetching}
      isError={query.isError}
      onRetry={() => query.refetch()}
      series={latencySeries(query.data)}
      kind="line"
      format={durationFormat}
      emptyLabel={t("latency.empty")}
      errorLabel={t("error.title")}
      retryLabel={t("error.retry")}
      range={range}
      dataThrough={query.data?.data_through}
      dataThroughLabel={t("dataThrough")}
      action={action}
    />
  );
}
