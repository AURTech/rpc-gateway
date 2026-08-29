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
  CachePerformanceCard,
  LatencyTrendCard,
  MethodTrendCard,
  NetworkTrendCard,
  OverallTrendCard,
  TrafficTrendCard,
} from "./usage-trend-cards";

// Two-up chart grid: stacks to one column below xl. Reused across every row.
const CHART_GRID = "grid grid-cols-1 gap-4 xl:grid-cols-2";

// The v2 summary endpoint shares the page-level range and network scope, and
// asks for the preceding window so the KPI tiles can show a change.
function kpiScopeFrom(filters: UsageChartFilters): UsageParams {
  return {
    range: filters.range,
    ...(filters.chain ? { chain: filters.chain } : {}),
    ...(filters.network ? { network: filters.network } : {}),
    compare: true,
  };
}

export function UsageContent() {
  const queryClient = useQueryClient();
  const isRefreshing = useIsFetching({ queryKey: usageKeys.all }) > 0;
  const [filters, setFilters] = useState<UsageChartFilters>({
    ...DEFAULT_USAGE_FILTERS,
  });

  const kpiScope = useMemo(() => kpiScopeFrom(filters), [filters]);

  const refreshUsage = () => {
    void queryClient.invalidateQueries({ queryKey: usageKeys.all });
  };

  return (
    <div className="flex flex-col gap-4">
      <UsageGlobalToolbar
        value={filters}
        onChange={setFilters}
        onRefresh={refreshUsage}
        isRefreshing={isRefreshing}
      />

      <UsageKpis scope={kpiScope} />

      <div className={CHART_GRID}>
        <OverallTrendCard filters={filters} />
        <MethodTrendCard filters={filters} />
        <NetworkTrendCard filters={filters} />
        <CachePerformanceCard filters={filters} />
        <TrafficTrendCard filters={filters} />
        <LatencyTrendCard filters={filters} />
      </div>
    </div>
  );
}
