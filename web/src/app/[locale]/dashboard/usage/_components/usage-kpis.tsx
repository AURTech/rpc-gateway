"use client";

import { Activity, ArrowDownUp, CheckCircle2, Gauge, Zap } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo } from "react";

import type { RpcUsageWindow, UsageParams } from "@/api/usage/client";
import {
  formatBytes,
  splitDuration,
} from "@/components/dashboard/usage-trend-chart";
import { KpiStrip, type KpiTileProps } from "@/components/patterns/kpi-strip";
import { Skeleton } from "@/components/ui/skeleton";
import { useUsageSummaryQuery } from "@/hooks/use-usage";
import { cn } from "@/lib/utils";

// Five tiles laid out across the page width; collapses to 2-up then 1-up.
const KPI_LAYOUT = "grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5";

/**
 * Usage KPI strip follows the page-level default range. Every tile reads from
 * the single `/v2/usage/summary` window, which folds calls, cache, latency and
 * traffic into one metrics block.
 */
export function UsageKpis({ scope }: { scope: UsageParams }) {
  const t = useTranslations("dashboard.usage.kpi");
  const locale = useLocale();

  const summary = useUsageSummaryQuery(scope);

  const tiles = useMemo<KpiTileProps[] | null>(() => {
    if (!summary.data) return null;
    return buildTiles({ summary: summary.data, locale, t });
  }, [summary.data, locale, t]);

  if (summary.isPending) {
    return <KpiStripSkeleton ariaLabel={t("ariaLabel")} />;
  }

  if (summary.isError || !tiles) {
    return (
      <ErrorTile
        title={t("error.title")}
        retryLabel={t("error.retry")}
        onRetry={() => summary.refetch()}
      />
    );
  }

  return (
    <KpiStrip ariaLabel={t("ariaLabel")} tiles={tiles} className={KPI_LAYOUT} />
  );
}

type BuildTilesArgs = {
  summary: RpcUsageWindow;
  locale: string;
  t: ReturnType<typeof useTranslations<"dashboard.usage.kpi">>;
};

function buildTiles({ summary, locale, t }: BuildTilesArgs): KpiTileProps[] {
  const compact = new Intl.NumberFormat(locale, {
    notation: "compact",
    maximumFractionDigits: 2,
  });
  const decimal2 = new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const integer = new Intl.NumberFormat(locale);

  // Same millisecond/second switch the latency chart uses, so the tile and the
  // card below it never disagree about the unit. Sub-second averages stay whole
  // milliseconds; seconds keep two decimals to preserve 10 ms of resolution.
  // `ms`/`s` are SI symbols and stay untranslated — they carry no locale.
  const latency = splitDuration(summary.avg_duration_ms);

  return [
    {
      label: t("totalCalls.label"),
      value: compact.format(summary.total_requests),
      icon: Activity,
    },
    {
      label: t("successRate.label"),
      value: decimal2.format(summary.success_rate * 100),
      unit: "%",
      icon: CheckCircle2,
    },
    {
      label: t("cacheHit.label"),
      value: decimal2.format(summary.cache_hit_rate * 100),
      unit: "%",
      icon: Zap,
    },
    {
      label: t("latency.label"),
      value:
        latency.unit === "s"
          ? decimal2.format(latency.value)
          : integer.format(Math.round(latency.value)),
      unit: latency.unit,
      icon: Gauge,
    },
    {
      label: t("traffic.label"),
      value: formatBytes(summary.total_traffic_bytes, 2),
      icon: ArrowDownUp,
    },
  ];
}

function KpiStripSkeleton({ ariaLabel }: { ariaLabel: string }) {
  return (
    <section aria-label={ariaLabel} aria-busy="true" className={KPI_LAYOUT}>
      {[0, 1, 2, 3, 4].map((i) => (
        <div
          key={i}
          className="flex min-h-36 flex-col rounded-xl bg-surface px-5 pb-4 pt-4 shadow-section"
        >
          <Skeleton className="h-3.5 w-24" />
          <div className="mt-auto flex flex-col gap-2 pt-3">
            <Skeleton className="h-8 w-24" />
            <Skeleton className="h-3 w-16" />
          </div>
        </div>
      ))}
    </section>
  );
}

function ErrorTile({
  title,
  retryLabel,
  onRetry,
}: {
  title: string;
  retryLabel: string;
  onRetry: () => void;
}) {
  return (
    <section
      role="alert"
      className={cn(
        "flex flex-col items-start gap-3 rounded-xl bg-surface px-5 py-5 shadow-section",
        "sm:flex-row sm:items-center sm:justify-between",
      )}
    >
      <div className="flex items-center gap-3">
        <span
          aria-hidden
          className="inline-flex size-2 rounded-full bg-danger"
        />
        <p className="text-md font-medium text-ink-900">{title}</p>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="rounded-md bg-ink-wash px-3 py-1.5 text-xs font-semibold text-ink-700 transition-colors hover:text-ink-900 focus-visible:outline-none"
      >
        {retryLabel}
      </button>
    </section>
  );
}
