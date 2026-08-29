"use client";

import { Activity, ArrowDownUp, CheckCircle2, Gauge, Zap } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo } from "react";

import type {
  RpcUsagePreviousWindow,
  RpcUsageWindow,
  UsageParams,
} from "@/api/usage/client";
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

// Below this the change rounds to zero at the precision each delta is printed
// with, so it is reported as "no change" instead of a signed hair.
const RELATIVE_EPSILON = 0.05;
const POINTS_EPSILON = 0.005;

type KpiDelta = NonNullable<KpiTileProps["delta"]>;

// How a metric's direction should be read. Volumes carry no verdict; rates are
// better when they rise; latency is better when it falls.
type DeltaTone = "neutral" | "growth" | "inverse";

/**
 * Usage KPI strip follows the page-level default range. Every tile reads from
 * the single `/v2/usage/summary` window, which folds calls, cache, latency and
 * traffic into one metrics block, plus the preceding window of the same span
 * that `compare` asks for.
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

type DeltaFactoryArgs = {
  previous: RpcUsagePreviousWindow | null;
  locale: string;
  t: ReturnType<typeof useTranslations<"dashboard.usage.kpi">>;
};

function semanticFor(tone: DeltaTone, rising: boolean): KpiDelta["semantic"] {
  if (tone === "neutral") return "neutral";
  if (tone === "growth") return rising ? "good" : "bad";
  return rising ? "bad" : "good";
}

// Volume metrics (calls, bytes, latency) compare as a relative change; a
// previous window of zero has no ratio, so the tile says the traffic is new.
function relativeDelta(
  { previous, locale, t }: DeltaFactoryArgs,
  {
    value,
    of,
    tone,
    enabled = true,
  }: {
    value: number;
    of: (window: RpcUsagePreviousWindow) => number;
    tone: DeltaTone;
    enabled?: boolean;
  },
): KpiDelta | undefined {
  if (!previous || !enabled) return undefined;
  const before = of(previous);
  if (before === 0) {
    if (value === 0) return undefined;
    return {
      label: t("comparison.new"),
      direction: "up",
      semantic: "neutral",
    };
  }
  const percent = new Intl.NumberFormat(locale, {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  const change = ((value - before) / before) * 100;
  if (Math.abs(change) < RELATIVE_EPSILON) {
    return {
      label: `${percent.format(0)}%`,
      direction: "neutral",
      semantic: "neutral",
    };
  }
  return {
    label: `${percent.format(Math.abs(change))}%`,
    direction: change > 0 ? "up" : "down",
    semantic: semanticFor(tone, change > 0),
  };
}

// Rates move in percentage points, not in percent of a percent: 99% → 99.5% is
// "+0.50 pp", never "+0.51%". `enabled` carries the previous window's
// denominator, because a rate over zero requests is reported as 0 and would
// otherwise read as a collapse.
function pointsDelta(
  { previous, locale }: DeltaFactoryArgs,
  {
    rate,
    of,
    enabled,
  }: {
    rate: number;
    of: (window: RpcUsagePreviousWindow) => number;
    enabled: (window: RpcUsagePreviousWindow) => boolean;
  },
): KpiDelta | undefined {
  if (!previous || !enabled(previous)) return undefined;
  const points = new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const change = (rate - of(previous)) * 100;
  if (Math.abs(change) < POINTS_EPSILON) {
    return {
      label: `${points.format(0)} pp`,
      direction: "neutral",
      semantic: "neutral",
    };
  }
  return {
    label: `${points.format(Math.abs(change))} pp`,
    direction: change > 0 ? "up" : "down",
    semantic: semanticFor("growth", change > 0),
  };
}

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

  // Split the settled byte label so the count-up can hold that unit fixed;
  // formatBytes emits "<mantissa> <unit>" and drops the decimals below 1 KB.
  const trafficText = formatBytes(summary.total_traffic_bytes, 2);
  const [trafficMantissa = "0", trafficUnit = "B"] = trafficText.split(" ");
  const traffic = {
    mantissa: Number(trafficMantissa),
    unit: trafficUnit,
    digits: trafficMantissa.includes(".") ? 2 : 0,
  };

  // One comparison window feeds every tile; the caption only appears on tiles
  // that could actually compute a change.
  const deltaArgs: DeltaFactoryArgs = {
    previous: summary.previous ?? null,
    locale,
    t,
  };
  const caption = t(`comparison.${summary.time_range}`);
  const callsDelta = relativeDelta(deltaArgs, {
    value: summary.total_requests,
    of: (window) => window.total_requests,
    tone: "neutral",
  });
  const successDelta = pointsDelta(deltaArgs, {
    rate: summary.success_rate,
    of: (window) => window.success_rate,
    enabled: (window) => window.total_requests > 0,
  });
  const cacheDelta = pointsDelta(deltaArgs, {
    rate: summary.cache_hit_rate,
    of: (window) => window.cache_hit_rate,
    enabled: (window) => window.cache_eligible_requests > 0,
  });
  const latencyDelta = relativeDelta(deltaArgs, {
    value: summary.avg_duration_ms,
    of: (window) => window.avg_duration_ms,
    tone: "inverse",
    enabled: (summary.previous?.total_requests ?? 0) > 0,
  });
  const trafficDelta = relativeDelta(deltaArgs, {
    value: summary.total_traffic_bytes,
    of: (window) => window.total_traffic_bytes,
    tone: "neutral",
  });

  // Each tile hands the count-up its raw number alongside the same formatter
  // that produced `value`, so every frame of the tween carries the tile's own
  // notation, precision and unit rather than a bare integer.
  return [
    {
      label: t("totalCalls.label"),
      value: compact.format(summary.total_requests),
      count: {
        to: summary.total_requests,
        format: (n: number) => compact.format(n),
      },
      icon: Activity,
      delta: callsDelta,
      caption: callsDelta ? caption : undefined,
    },
    {
      label: t("successRate.label"),
      value: decimal2.format(summary.success_rate * 100),
      count: {
        to: summary.success_rate * 100,
        format: (n: number) => decimal2.format(n),
      },
      unit: "%",
      icon: CheckCircle2,
      delta: successDelta,
      caption: successDelta ? caption : undefined,
    },
    {
      label: t("cacheHit.label"),
      value: decimal2.format(summary.cache_hit_rate * 100),
      count: {
        to: summary.cache_hit_rate * 100,
        format: (n: number) => decimal2.format(n),
      },
      unit: "%",
      icon: Zap,
      delta: cacheDelta,
      caption: cacheDelta ? caption : undefined,
    },
    {
      label: t("latency.label"),
      value:
        latency.unit === "s"
          ? decimal2.format(latency.value)
          : integer.format(Math.round(latency.value)),
      count: {
        to: latency.value,
        format: (n: number) =>
          latency.unit === "s"
            ? decimal2.format(n)
            : integer.format(Math.round(n)),
      },
      unit: latency.unit,
      icon: Gauge,
      delta: latencyDelta,
      caption: latencyDelta ? caption : undefined,
    },
    {
      label: t("traffic.label"),
      value: trafficMantissa,
      // Tweens the mantissa only. Handing the raw byte count to formatBytes
      // would re-pick the unit on every frame and walk the label B → KB → MB,
      // changing its width as it went.
      count: {
        to: traffic.mantissa,
        format: (n: number) => n.toFixed(traffic.digits),
      },
      unit: traffic.unit,
      icon: ArrowDownUp,
      delta: trafficDelta,
      caption: trafficDelta ? caption : undefined,
    },
  ];
}

function KpiStripSkeleton({ ariaLabel }: { ariaLabel: string }) {
  return (
    <section aria-label={ariaLabel} aria-busy="true" className={KPI_LAYOUT}>
      {[0, 1, 2, 3, 4].map((i) => (
        <div
          key={i}
          className="flex min-h-30 flex-col rounded-xl bg-surface px-4 py-3 shadow-section"
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
