"use client";

import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import type { UsageParams } from "@/api/usage/client";
import { usageKeys } from "@/hooks/use-usage";

import {
  DEFAULT_USAGE_FILTERS,
  type UsageChartFilters,
  UsageGlobalToolbar,
} from "./usage-filter-bar";
import { UsageKpis } from "./usage-kpis";
import {
  CacheByMethodTrendCard,
  CacheTrendCard,
  LatencyTrendCard,
  MethodTrendCard,
  NetworkTrendCard,
  OverallTrendCard,
  TrafficTrendCard,
} from "./usage-trend-cards";

// Two-up chart grid: stacks to one column below xl. Reused across every row.
const CHART_GRID = "grid grid-cols-1 gap-4 xl:grid-cols-2";

const CHART_IDS = [
  "overall",
  "methods",
  "network",
  "cache",
  "cacheByMethod",
  "traffic",
  "latency",
] as const;

type UsageChartId = (typeof CHART_IDS)[number];
type UsageChartFilterMap = Record<UsageChartId, UsageChartFilters>;

function chartFilterMapFrom(filters: UsageChartFilters): UsageChartFilterMap {
  return Object.fromEntries(
    CHART_IDS.map((id) => [id, { ...filters }]),
  ) as UsageChartFilterMap;
}

// The v2 summary endpoint shares the page-level range and network scope.
function kpiScopeFrom(filters: UsageChartFilters): UsageParams {
  return {
    range: filters.range,
    ...(filters.chain ? { chain: filters.chain } : {}),
    ...(filters.network ? { network: filters.network } : {}),
  };
}

export function UsageContent() {
  const queryClient = useQueryClient();
  const isRefreshing = useIsFetching({ queryKey: usageKeys.all }) > 0;
  const [globalFilters, setGlobalFilters] = useState<UsageChartFilters>({
    ...DEFAULT_USAGE_FILTERS,
  });
  const [chartFilters, setChartFilters] = useState<UsageChartFilterMap>(() =>
    chartFilterMapFrom(DEFAULT_USAGE_FILTERS),
  );

  const kpiScope = useMemo(() => kpiScopeFrom(globalFilters), [globalFilters]);

  const setChartFilter = (id: UsageChartId) => (next: UsageChartFilters) => {
    setChartFilters((current) => ({ ...current, [id]: next }));
  };

  const applyGlobalFiltersToAllCharts = () => {
    setChartFilters(chartFilterMapFrom(globalFilters));
  };

  const refreshUsage = () => {
    void queryClient.invalidateQueries({ queryKey: usageKeys.all });
  };

  return (
    <div className="flex flex-col gap-4">
      <UsageGlobalToolbar
        value={globalFilters}
        onChange={setGlobalFilters}
        onApplyToAll={applyGlobalFiltersToAllCharts}
        onRefresh={refreshUsage}
        isRefreshing={isRefreshing}
      />

      <UsageKpis scope={kpiScope} />

      <div className={CHART_GRID}>
        <OverallTrendCard
          filters={chartFilters.overall}
          onFiltersChange={setChartFilter("overall")}
        />
        <MethodTrendCard
          filters={chartFilters.methods}
          onFiltersChange={setChartFilter("methods")}
        />
        <NetworkTrendCard
          filters={chartFilters.network}
          onFiltersChange={setChartFilter("network")}
        />
        <CacheTrendCard
          filters={chartFilters.cache}
          onFiltersChange={setChartFilter("cache")}
        />
        <CacheByMethodTrendCard
          filters={chartFilters.cacheByMethod}
          onFiltersChange={setChartFilter("cacheByMethod")}
        />
        <TrafficTrendCard
          filters={chartFilters.traffic}
          onFiltersChange={setChartFilter("traffic")}
        />
        <LatencyTrendCard
          filters={chartFilters.latency}
          onFiltersChange={setChartFilter("latency")}
        />
      </div>
    </div>
  );
}
