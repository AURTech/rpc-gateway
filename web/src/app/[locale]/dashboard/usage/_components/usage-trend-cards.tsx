"use client";

import { useTranslations } from "next-intl";
import { useDeferredValue, useMemo, useState } from "react";

import type { RpcUsageByEndpoint, RpcUsageSeries } from "@/api/usage/client";
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
  type Series,
  TrendChartCard,
  trafficSeries,
} from "@/components/dashboard/usage-trend-chart";
import { Tabs } from "@/components/ui/tabs";
import {
  useUsageByEndpointQuery,
  useUsageByMethodQuery,
  useUsageByNetworkQuery,
  useUsageSeriesQuery,
} from "@/hooks/use-usage";

import type { UsageChartFilters, UsageScope } from "./usage-filter-bar";

export type { UsageScope };

const EMPTY_SCOPE: UsageScope = {};
const CACHE_METHOD_LIMIT = 8;
const NETWORK_METRIC_LIMIT = 100;

type UsageTrendCardProps = {
  scope?: UsageScope;
  filters: UsageChartFilters;
  showDataThrough?: boolean;
};

// Every card is driven by the filters its page owns — the Usage toolbar or the
// app detail Metrics tab — so no card carries its own range or scope control.
function useCardFilters({ scope = EMPTY_SCOPE, filters }: UsageTrendCardProps) {
  const deferredScope = useDeferredValue(scope);
  const deferredFilters = useDeferredValue(filters);
  const queryFilters = useMemo(
    () => ({
      ...deferredScope,
      ...(deferredFilters.chain ? { chain: deferredFilters.chain } : {}),
      ...(deferredFilters.network ? { network: deferredFilters.network } : {}),
      range: deferredFilters.range,
    }),
    [deferredScope, deferredFilters],
  );

  return { range: queryFilters.range, filters: queryFilters };
}

export function MethodTrendCard(props: UsageTrendCardProps) {
  const t = useTranslations("dashboard.usage");
  const { range, filters } = useCardFilters(props);
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
      dataThrough={
        props.showDataThrough === false ? undefined : query.data?.data_through
      }
      dataThroughLabel={
        props.showDataThrough === false ? undefined : t("dataThrough")
      }
    />
  );
}

// Overall request volume over time, split success (green) vs. failure (red).
// Backed by `/v2/usage/series`.
export function OverallTrendCard(props: UsageTrendCardProps) {
  const t = useTranslations("dashboard.usage");
  const { range, filters } = useCardFilters(props);
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
      dataThrough={
        props.showDataThrough === false ? undefined : query.data?.data_through
      }
      dataThroughLabel={
        props.showDataThrough === false ? undefined : t("dataThrough")
      }
    />
  );
}

export function AppRequestActivityTrendCard(props: UsageTrendCardProps) {
  const t = useTranslations("dashboard.usage");
  const { range, filters } = useCardFilters(props);
  const requests = useUsageSeriesQuery(filters);
  const attempts = useUsageByEndpointQuery(filters);

  return (
    <TrendChartCard
      title={t("overall.title")}
      subhead={t("overall.appSubhead")}
      isPending={requests.isPending || attempts.isPending}
      isFetching={requests.isFetching || attempts.isFetching}
      isError={requests.isError || attempts.isError}
      onRetry={() => {
        void requests.refetch();
        void attempts.refetch();
      }}
      series={requestActivitySeries(requests.data, attempts.data, {
        success: t("overall.success"),
        failure: t("overall.failure"),
        attempts: t("overall.upstreamAttempts"),
      })}
      kind="line"
      emptyLabel={t("overall.empty")}
      errorLabel={t("error.title")}
      retryLabel={t("error.retry")}
      range={range}
      dataThrough={
        props.showDataThrough === false
          ? undefined
          : (attempts.data?.data_through ?? requests.data?.data_through)
      }
      dataThroughLabel={
        props.showDataThrough === false ? undefined : t("dataThrough")
      }
    />
  );
}

export function requestActivitySeries(
  requests: RpcUsageSeries | undefined,
  attempts: RpcUsageByEndpoint | undefined,
  labels: { success: string; failure: string; attempts: string },
): Series[] {
  if (!requests || !attempts) return [];

  const requestSeries = overallSeries(requests, labels);
  const attemptsByBucket = new Map<string, number>();
  for (const item of attempts.items) {
    for (const point of item.points) {
      attemptsByBucket.set(
        point.bucket_start,
        (attemptsByBucket.get(point.bucket_start) ?? 0) + point.total_attempts,
      );
    }
  }
  for (const point of attempts.other_points) {
    attemptsByBucket.set(
      point.bucket_start,
      (attemptsByBucket.get(point.bucket_start) ?? 0) + point.total_attempts,
    );
  }

  if (
    requestSeries.length === 0 &&
    ![...attemptsByBucket.values()].some((value) => value > 0)
  ) {
    return [];
  }

  return [
    ...requestSeries,
    {
      key: "attempts",
      label: labels.attempts,
      color: "var(--warning)",
      points: requests.items.map((point) => ({
        bucket_start: point.bucket_start,
        value: attemptsByBucket.get(point.bucket_start) ?? 0,
      })),
    },
  ];
}

export function NetworkTrendCard(props: UsageTrendCardProps) {
  const t = useTranslations("dashboard.usage");
  const { range, filters } = useCardFilters(props);
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
      dataThrough={
        props.showDataThrough === false ? undefined : query.data?.data_through
      }
      dataThroughLabel={
        props.showDataThrough === false ? undefined : t("dataThrough")
      }
    />
  );
}

const CACHE_VIEWS = ["overTime", "method"] as const;

type CacheView = (typeof CACHE_VIEWS)[number];

// One card for cache performance. "Over time" reads hit rate per chain/network,
// "Method" ranks the cache-eligible RPC methods. Both queries stay mounted so
// switching views is instant, and the page issues the same two requests it did
// when these were two separate cards.
export function CachePerformanceCard(props: UsageTrendCardProps) {
  const t = useTranslations("dashboard.usage");
  const { range, filters } = useCardFilters(props);
  const [view, setView] = useState<CacheView>("overTime");

  const networkQuery = useUsageByNetworkQuery({
    ...filters,
    limit: NETWORK_METRIC_LIMIT,
  });
  const methodQuery = useUsageByMethodQuery({
    ...filters,
    rank_by: "cache_eligible_requests",
    limit: CACHE_METHOD_LIMIT,
  });

  const query = view === "overTime" ? networkQuery : methodQuery;
  const series =
    view === "overTime"
      ? cacheSeries(networkQuery.data)
      : cacheByMethodSeries(methodQuery.data);

  const viewOptions = CACHE_VIEWS.map((option) => ({
    value: option,
    label: t(`cache.views.${option}`),
  }));

  return (
    <TrendChartCard
      title={t("cache.title")}
      subhead={
        view === "overTime" ? t("cache.subhead") : t("cacheByMethod.subhead")
      }
      isPending={query.isPending}
      isFetching={query.isFetching}
      isError={query.isError}
      onRetry={() => query.refetch()}
      series={series}
      kind="line"
      format={percentFormat}
      emptyLabel={
        view === "overTime" ? t("cache.empty") : t("cacheByMethod.empty")
      }
      errorLabel={t("error.title")}
      retryLabel={t("error.retry")}
      range={range}
      dataThrough={
        props.showDataThrough === false ? undefined : query.data?.data_through
      }
      dataThroughLabel={
        props.showDataThrough === false ? undefined : t("dataThrough")
      }
      action={
        <Tabs
          mode="segmented"
          value={view}
          onChange={setView}
          options={viewOptions}
          ariaLabel={t("cache.viewAriaLabel")}
        />
      }
    />
  );
}

export function TrafficTrendCard(props: UsageTrendCardProps) {
  const t = useTranslations("dashboard.usage");
  const { range, filters } = useCardFilters(props);
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
      dataThrough={
        props.showDataThrough === false ? undefined : query.data?.data_through
      }
      dataThroughLabel={
        props.showDataThrough === false ? undefined : t("dataThrough")
      }
    />
  );
}

export function LatencyTrendCard(props: UsageTrendCardProps) {
  const t = useTranslations("dashboard.usage");
  const { range, filters } = useCardFilters(props);
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
      dataThrough={
        props.showDataThrough === false ? undefined : query.data?.data_through
      }
      dataThroughLabel={
        props.showDataThrough === false ? undefined : t("dataThrough")
      }
    />
  );
}
