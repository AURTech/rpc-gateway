"use client";

import { useTranslations } from "next-intl";
import { useDeferredValue, useMemo, useState } from "react";

import { RPC_USAGE_RANGES, type RpcUsageRange } from "@/api/usage/client";
import {
  bytesFormat,
  overallSeries,
  TrendChartCard,
  trafficSeries,
} from "@/components/dashboard/usage-trend-chart";
import { Tabs } from "@/components/ui/tabs";
import { useUsageSeriesQuery } from "@/hooks/use-usage";

/**
 * Overview's request and traffic trends share one range selector and one
 * `/v2/usage/series` query. Account-scoped by default; `appId` narrows the
 * series to a single app (the app Overview page).
 */
export function OverviewChartsSection({ appId }: { appId?: string }) {
  const t = useTranslations("dashboard.overview.trend");
  const [range, setRange] = useState<RpcUsageRange>("weekly");
  // The pill follows `range` immediately so the slide animation fires on click;
  // the heavy recharts cards follow the deferred value, so their re-render runs
  // at low priority and never stutters the concurrent pill animation.
  const deferredRange = useDeferredValue(range);
  const params = useMemo(
    () => ({ range: deferredRange, ...(appId ? { app_id: appId } : {}) }),
    [deferredRange, appId],
  );
  const query = useUsageSeriesQuery(params);

  const rangeOptions = useMemo(
    () =>
      RPC_USAGE_RANGES.map((range) => ({
        value: range,
        label: t(`ranges.${range}`),
      })),
    [t],
  );

  const calls = useMemo(
    () =>
      overallSeries(query.data, {
        success: t("calls.success"),
        failure: t("calls.failure"),
      }),
    [query.data, t],
  );
  const traffic = useMemo(
    () =>
      trafficSeries(query.data, {
        request: t("traffic.upload"),
        response: t("traffic.download"),
      }),
    [query.data, t],
  );

  return (
    <section aria-label={t("ariaLabel")} className="flex flex-col gap-4">
      <div className="flex justify-end">
        <Tabs
          mode="segmented"
          value={range}
          onChange={setRange}
          options={rangeOptions}
          ariaLabel={t("rangeAriaLabel")}
        />
      </div>
      <div className="flex flex-col gap-4">
        <TrendChartCard
          title={t("calls.title")}
          subhead={t("calls.subhead")}
          isPending={query.isPending}
          isError={query.isError}
          onRetry={() => query.refetch()}
          series={calls}
          kind="area"
          emptyLabel={t("calls.empty")}
          errorLabel={t("error.title")}
          retryLabel={t("error.retry")}
          range={deferredRange}
          dataThrough={query.data?.data_through}
          dataThroughLabel={t("dataThrough")}
        />
        <TrendChartCard
          title={t("traffic.title")}
          subhead={t("traffic.subhead")}
          isPending={query.isPending}
          isError={query.isError}
          onRetry={() => query.refetch()}
          series={traffic}
          kind="area-stacked"
          format={bytesFormat}
          emptyLabel={t("traffic.empty")}
          errorLabel={t("error.title")}
          retryLabel={t("error.retry")}
          range={deferredRange}
          dataThrough={query.data?.data_through}
          dataThroughLabel={t("dataThrough")}
        />
      </div>
    </section>
  );
}
