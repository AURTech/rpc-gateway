"use client";

import { useLocale } from "next-intl";
import { type ReactElement, type ReactNode, useId, useMemo } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  XAxis,
  YAxis,
} from "recharts";

import type {
  RpcUsageByMethod,
  RpcUsageByNetwork,
  RpcUsageRange,
  RpcUsageSeries,
} from "@/api/usage/client";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  type ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export const PALETTE = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--chart-6)",
  "var(--chart-7)",
  "var(--chart-8)",
] as const;

// A single plotted point, reduced to the one numeric value the area chart draws.
// Adapters below pick that value (call volume vs upstream attempts) so the chart
// itself stays agnostic to which usage counter it's rendering.
export type SeriesPoint = {
  bucket_start: string;
  value: number;
};

export type Series = {
  key: string;
  label: string;
  points: SeriesPoint[];
  // Optional explicit colour (a CSS custom-property ref like `var(--positive)`).
  // Falls back to the rotating PALETTE when omitted. Used by the success/failure
  // chart to pin semantic green/red instead of arbitrary palette slots.
  color?: string;
};

// Series endpoints zero-fill every bucket in the window, so `items.length`
// can't distinguish "no activity" from "activity with zero-valued metric".
// Each adapter passes the domain signal (calls / attempts / bytes / eligible
// cache calls) through this guard: a window with no signal renders the card's
// empty state instead of a flat all-zero chart.
function hasSignal<T>(
  items: readonly T[],
  signal: (item: T) => number,
): boolean {
  return items.some((item) => signal(item) > 0);
}

export function methodSeries(data: RpcUsageByMethod | undefined): Series[] {
  if (!data) return [];
  if (
    !hasSignal(
      data.items.flatMap((item) => item.points),
      (p) => p.total_requests,
    )
  ) {
    return [];
  }
  return data.items.map((item) => ({
    key: sanitizeKey(item.method),
    label: item.method,
    points: item.points.map((p) => ({
      bucket_start: p.bucket_start,
      value: p.total_requests,
    })),
  }));
}

export function cacheByMethodSeries(
  data: RpcUsageByMethod | undefined,
): Series[] {
  if (!data) return [];
  if (
    !hasSignal(
      data.items.flatMap((item) => item.points),
      (p) => p.cache_eligible_requests,
    )
  ) {
    return [];
  }
  return data.items.map((item) => ({
    key: sanitizeKey(item.method),
    label: item.method,
    points: item.points.map((p) => ({
      bucket_start: p.bucket_start,
      value: p.cache_hit_rate,
    })),
  }));
}

// v2 total trend: successful vs. failed requests off `/v2/usage/series`. Same
// green/red split as the old Overview `successFailureSeries`, but reading the
// unified `successful_requests` / `failed_requests` fields.
export function overallSeries(
  data: RpcUsageSeries | undefined,
  labels: { success: string; failure: string },
): Series[] {
  if (!data || !hasSignal(data.items, (p) => p.total_requests)) return [];
  return [
    {
      key: "success",
      label: labels.success,
      color: "var(--positive)",
      points: data.items.map((p) => ({
        bucket_start: p.bucket_start,
        value: p.successful_requests,
      })),
    },
    {
      key: "failure",
      label: labels.failure,
      color: "var(--danger)",
      points: data.items.map((p) => ({
        bucket_start: p.bucket_start,
        value: p.failed_requests,
      })),
    },
  ];
}

export function networkSeries(data: RpcUsageByNetwork | undefined): Series[] {
  if (!data) return [];
  if (
    !hasSignal(
      data.items.flatMap((item) => item.points),
      (p) => p.total_requests,
    )
  ) {
    return [];
  }
  return data.items.map((item) => ({
    key: sanitizeKey(`${item.chain}_${item.network}`),
    label: `${item.chain_label} · ${item.network_label}`,
    points: item.points.map((p) => ({
      bucket_start: p.bucket_start,
      value: p.total_requests,
    })),
  }));
}

// Cache hit rate by chain/network. Networks without any cache-eligible traffic
// in the window are omitted because 0 would otherwise conflate "not
// applicable" with a measured zero-percent hit rate.
export function cacheSeries(data: RpcUsageByNetwork | undefined): Series[] {
  if (!data) return [];
  return data.items
    .filter((item) =>
      hasSignal(item.points, (point) => point.cache_eligible_requests),
    )
    .map((item) => ({
      key: sanitizeKey(`${item.chain}_${item.network}`),
      label: `${item.chain_label} · ${item.network_label}`,
      points: item.points.map((p) => ({
        bucket_start: p.bucket_start,
        value: p.cache_hit_rate,
      })),
    }));
}

// Traffic series: request vs. response bytes as two neutral palette bands. Both
// request and response data come from the unified v2 series. Rendered with
// `bytesFormat` (KB/MB/GB axis + tooltip).
export function trafficSeries(
  data: RpcUsageSeries | undefined,
  labels: { request: string; response: string },
): Series[] {
  if (
    !data ||
    !hasSignal(
      data.items,
      (p) => p.total_request_bytes + p.total_response_bytes,
    )
  ) {
    return [];
  }
  return [
    {
      key: "request_bytes",
      label: labels.request,
      points: data.items.map((p) => ({
        bucket_start: p.bucket_start,
        value: p.total_request_bytes,
      })),
    },
    {
      key: "response_bytes",
      label: labels.response,
      points: data.items.map((p) => ({
        bucket_start: p.bucket_start,
        value: p.total_response_bytes,
      })),
    },
  ];
}

// End-to-end average request duration by chain/network. Each line uses the
// server's weighted duration for that network and remains independent.
export function latencySeries(data: RpcUsageByNetwork | undefined): Series[] {
  if (!data) return [];
  return data.items
    .filter((item) => hasSignal(item.points, (point) => point.total_requests))
    .map((item) => ({
      key: sanitizeKey(`${item.chain}_${item.network}`),
      label: `${item.chain_label} · ${item.network_label}`,
      points: item.points.map((p) => ({
        bucket_start: p.bucket_start,
        value: p.avg_duration_ms,
      })),
    }));
}

// CSS custom property names must be a valid identifier; map any non-identifier
// character to `_` so the ChartContainer's emitted `--color-<key>` is parseable.
export function sanitizeKey(raw: string): string {
  return raw.replace(/[^a-zA-Z0-9_-]/g, "_");
}

// The Y-axis spec a chart draws with: ceiling, tick positions, and whether the
// axis renders fractional ticks.
export type AxisSpec = {
  top: number;
  ticks: number[];
  allowDecimals: boolean;
  // Optional override for the axis tick labels. Used when the derived tick step
  // needs more precision than the format's default compact rendering — a percent
  // axis topping out at 0.3% would otherwise label every tick "0%".
  tickFormat?: (value: number) => string;
};

// Opt-in value formatting for a chart's Y axis + tooltip. Charts that render raw
// counts pass nothing and keep the default integer axis; the presets below cover
// percentages, byte sizes and durations.
export type ValueFormat = {
  // Derive the ceiling/ticks/decimals from the tallest plotted value.
  axis: (dataMax: number) => AxisSpec;
  // Render one value. `compact` = an axis tick (short); false = a tooltip (fuller).
  format: (value: number, compact: boolean) => string;
  // Optional wider Y axis for long formatted labels such as "238.4 MB".
  // This affects only the chart area, not the card header.
  axisWidth?: number;
};

// Cache hit-rate: values are a 0..1 fraction. A formatter alone can't work here —
// `niceStep` floors at 1, so `niceAxis(≤1)` collapses to [0,1]; percent needs an
// axis of its own, built from `PERCENT_STEPS`.
export const percentFormat: ValueFormat = {
  axis: (dataMax) => percentAxis(dataMax),
  format: (v, compact) =>
    // Rates below 1% would all render "0.0%" in a tooltip, so give the small end
    // an extra digit. Axis ticks get their precision from `percentAxis`.
    `${(v * 100).toFixed(compact ? 0 : v > 0 && v < 0.01 ? 2 : 1)}%`,
};

// Tick steps a percent axis may use, as 0..1 fractions (0.1% … 100%). Every
// entry divides 100% into round labels.
const PERCENT_STEPS: readonly number[] = [
  0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1,
];

// Percent axis fitted to the observed peak rather than pinned at 100%. A window
// where every method sits under 5% would otherwise draw as a flat line along the
// baseline, indistinguishable from zero. The ceiling never exceeds 100% and the
// baseline stays 0, so bar heights and line levels remain comparable.
export function percentAxis(dataMax: number, targetTicks = 4): AxisSpec {
  const peak = Math.min(Math.max(dataMax, 0), 1);
  // No measured rate at all: keep the familiar full-scale axis instead of
  // magnifying a flat zero line.
  if (peak <= 0) {
    return { top: 1, ticks: [0, 0.25, 0.5, 0.75, 1], allowDecimals: true };
  }

  const step = pickPercentStep(peak, targetTicks);
  const divisions = Math.max(1, percentDivisions(peak, step));
  const ticks: number[] = [];
  for (let i = 0; i <= divisions; i += 1) {
    // Accumulating `i * step` keeps ticks free of the drift that repeated
    // fractional addition would introduce.
    ticks.push(roundToGrid(i * step));
  }

  return {
    top: ticks[ticks.length - 1],
    ticks,
    allowDecimals: true,
    tickFormat: (value) =>
      `${(value * 100).toFixed(decimalDigits(step * 100))}%`,
  };
}

// Pick the step whose ceiling sits closest above the peak while keeping the
// gridline count readable (2..targetTicks divisions). Ties go to the finer step,
// so the axis carries as many labelled gridlines as it can without overshooting:
// a 42% peak lands on 0.25 (top 50%) rather than 0.2 (top 60%). Peaks too small
// for two divisions of the finest step fall back to that step.
function pickPercentStep(peak: number, targetTicks: number): number {
  let step = PERCENT_STEPS[0];
  let bestTop = Number.POSITIVE_INFINITY;
  for (const candidate of PERCENT_STEPS) {
    const divisions = percentDivisions(peak, candidate);
    if (divisions < 2 || divisions > targetTicks) continue;
    const top = divisions * candidate;
    if (top < bestTop) {
      bestTop = top;
      step = candidate;
    }
  }
  return step;
}

// Divisions needed to cover `peak`. The epsilon absorbs binary-float division
// error (0.03 / 0.01 is 2.9999999999999996) so a peak sitting exactly on the
// grid doesn't buy an extra empty division.
function percentDivisions(peak: number, step: number): number {
  return Math.ceil(peak / step - 1e-9);
}

// Fractional digits that render `value` exactly: 25 → 0, 0.5 → 1, 2.5 → 1.
// Axis steps are short decimals by construction, so three places is the ceiling.
// Deriving this from the magnitude instead would round 2.5 down to "3".
function decimalDigits(value: number): number {
  for (let digits = 0; digits < 3; digits += 1) {
    if (Math.abs(value - Number(value.toFixed(digits))) < 1e-9) return digits;
  }
  return 3;
}

// Strip binary-float drift from a tick: 3 * 0.1 is 0.30000000000000004, which
// recharts would treat as a value off the grid. Every PERCENT_STEPS entry has at
// most three decimals and multiplies by at most `targetTicks`, so six decimals
// preserve the intended value exactly.
function roundToGrid(value: number): number {
  return Number(value.toFixed(6));
}

// Traffic: byte counts. Reuse `niceAxis` for the tick *positions* (raw whole
// bytes) and only re-label them as KB/MB/GB.
export const bytesFormat: ValueFormat = {
  axis: (max) => ({ ...niceAxis(max), allowDecimals: false }),
  format: (v, compact) => formatBytes(v, compact ? 1 : 2),
  axisWidth: 80,
};

const MS_PER_SECOND = 1000;

export type DurationUnit = "ms" | "s";

// Latency is measured in milliseconds, but past a second the unit stops doing
// its job: "1,234 ms" makes the reader divide before they know what they're
// looking at. Anything from 1000 ms up is reported in seconds instead.
export function splitDuration(ms: number): {
  value: number;
  unit: DurationUnit;
} {
  return ms >= MS_PER_SECOND
    ? { value: ms / MS_PER_SECOND, unit: "s" }
    : { value: ms, unit: "ms" };
}

export const durationFormat: ValueFormat = {
  axis: (max) => durationAxis(max),
  format: (value, compact) => {
    const { value: scaled, unit } = splitDuration(value);
    const digits = unit === "s" ? (compact ? 1 : 2) : compact ? 0 : 1;
    return `${scaled.toLocaleString(undefined, {
      maximumFractionDigits: digits,
    })} ${unit}`;
  },
  axisWidth: 72,
};

// A latency axis carries one unit across all of its ticks. Letting each tick
// pick its own would print "500 ms" and "1 s" on the same axis, where the
// gridlines no longer read as an evenly spaced scale — so the unit comes from
// the ceiling and the tick precision from the step.
export function durationAxis(dataMax: number): AxisSpec {
  const { top, ticks } = niceAxis(dataMax);
  const { unit } = splitDuration(top);
  const divisor = unit === "s" ? MS_PER_SECOND : 1;
  const step = (ticks.length > 1 ? ticks[1] - ticks[0] : top) / divisor;
  const digits = decimalDigits(step);

  return {
    top,
    ticks,
    allowDecimals: true,
    tickFormat: (value) =>
      `${(value / divisor).toLocaleString(undefined, {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      })} ${unit}`,
  };
}

const BYTE_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"] as const;

const COMPACT_NUMBER_UNITS = [
  { threshold: 1_000_000_000_000, suffix: "t" },
  { threshold: 1_000_000_000, suffix: "b" },
  { threshold: 1_000_000, suffix: "m" },
  { threshold: 1_000, suffix: "k" },
] as const;

// Keep count-axis labels short while leaving tooltip values exact. One decimal
// preserves useful precision between powers of ten (for example, 1.5k), and
// values that round across a boundary are promoted to the next unit.
export function formatCompactNumber(value: number, locale?: string): string {
  const absoluteValue = Math.abs(value);
  const unitIndex = COMPACT_NUMBER_UNITS.findIndex(
    (unit) => absoluteValue >= unit.threshold,
  );

  if (unitIndex === -1) {
    return value.toLocaleString(locale, { maximumFractionDigits: 1 });
  }

  let selectedIndex = unitIndex;
  let scaled = value / COMPACT_NUMBER_UNITS[selectedIndex].threshold;
  let rounded = Math.round(scaled * 10) / 10;

  if (Math.abs(rounded) >= 1_000 && selectedIndex > 0) {
    selectedIndex -= 1;
    scaled = value / COMPACT_NUMBER_UNITS[selectedIndex].threshold;
    rounded = Math.round(scaled * 10) / 10;
  }

  return `${rounded.toLocaleString(locale, {
    maximumFractionDigits: 1,
    useGrouping: false,
  })}${COMPACT_NUMBER_UNITS[selectedIndex].suffix}`;
}

// Human-readable byte size (1024-based). `digits` controls the fractional places
// on scaled units; whole bytes render without a fraction.
export function formatBytes(value: number, digits: number): string {
  if (value <= 0) return "0 B";
  const exp = Math.min(
    Math.floor(Math.log(value) / Math.log(1024)),
    BYTE_UNITS.length - 1,
  );
  const scaled = value / 1024 ** exp;
  return `${scaled.toFixed(exp === 0 ? 0 : digits)} ${BYTE_UNITS[exp]}`;
}

export type TrendChartCardProps = {
  title: string;
  subhead: string;
  isPending: boolean;
  isError: boolean;
  onRetry: () => void;
  series: Series[];
  emptyLabel: string;
  errorLabel: string;
  retryLabel: string;
  range: RpcUsageRange;
  dataThrough?: string;
  dataThroughLabel?: string;
  // How the series are drawn. Pick by data semantics:
  //   • "area"         — a single volume band (default).
  //   • "area-stacked" — volumes that compose a total (request+response bytes).
  //   • "line"         — rates and averages (percentages, latency): levels,
  //                      not volumes, so no filled area.
  //   • "bar-stacked"  — per-category composition of a count (calls by
  //                      method/network): one bar per bucket, stacked slices.
  kind?: TrendChartKind;
  // True while a background refetch is in flight (filter change with
  // `keepPreviousData`). Dims the stale chart instead of collapsing to a
  // skeleton.
  isFetching?: boolean;
  // Optional value formatting for the Y axis + tooltip (percent / bytes / ms).
  // Omitting it keeps the default integer-count axis every existing card relies
  // on, byte-for-byte unchanged.
  format?: ValueFormat;
  // Optional controls pinned to the card's top-right corner (e.g. the per-card
  // range toggle or the hero card's scope filters). Omitting it keeps the
  // header as a plain title block — overview's cards rely on that.
  action?: ReactNode;
};

export type TrendChartKind = "area" | "area-stacked" | "line" | "bar-stacked";

export function hasSingleBucket(bucketCount: number): boolean {
  return bucketCount === 1;
}

export function TrendChartCard(props: TrendChartCardProps) {
  const locale = useLocale();
  const formattedDataThrough = props.dataThrough
    ? new Intl.DateTimeFormat(locale, {
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(new Date(props.dataThrough))
    : null;

  return (
    <Card className="gap-4">
      <CardHeader className="has-data-[slot=card-action]:grid-cols-1 sm:has-data-[slot=card-action]:grid-cols-[1fr_auto]">
        <CardTitle className="text-lg text-ink-900">{props.title}</CardTitle>
        <CardDescription className="text-xs">{props.subhead}</CardDescription>
        {props.action ? (
          <CardAction className="col-start-1 row-span-1 row-start-3 flex flex-wrap items-center gap-2 justify-self-start sm:col-start-2 sm:row-span-2 sm:row-start-1 sm:justify-self-end">
            {props.action}
          </CardAction>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-2">
        <ChartBody {...props} />
        {formattedDataThrough && props.dataThroughLabel ? (
          <p className="text-right text-xs text-ink-500 tabular-nums">
            {props.dataThroughLabel}{" "}
            <time dateTime={props.dataThrough}>{formattedDataThrough}</time>
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function ChartBody({
  isPending,
  isError,
  onRetry,
  series,
  emptyLabel,
  errorLabel,
  retryLabel,
  range,
  kind = "area",
  isFetching,
  format,
}: TrendChartCardProps) {
  if (isPending && series.length === 0) {
    return <Skeleton className="h-72 w-full rounded-xl" />;
  }

  if (isError && series.length === 0) {
    return (
      <div
        role="alert"
        className="flex flex-col items-start gap-3 rounded-xl bg-ink-wash p-5 sm:flex-row sm:items-center sm:justify-between"
      >
        <div className="flex items-center gap-3">
          <span
            aria-hidden
            className="inline-flex size-2 rounded-full bg-danger"
          />
          <p className="text-md font-medium text-ink-900">{errorLabel}</p>
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="rounded-md bg-surface px-3 py-1.5 text-xs font-semibold text-ink-700 transition-colors hover:text-ink-900 focus-visible:text-ink-900 focus-visible:outline-none"
        >
          {retryLabel}
        </button>
      </div>
    );
  }

  if (series.length === 0) {
    if (isFetching) {
      return <Skeleton className="h-72 w-full rounded-xl" />;
    }

    return (
      <div className="flex h-72 items-center justify-center rounded-xl bg-ink-wash text-md text-ink-500">
        {emptyLabel}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "transition-opacity",
        (isFetching || isError) && "opacity-60",
      )}
    >
      <TrendChart series={series} range={range} kind={kind} format={format} />
    </div>
  );
}

function TrendChart({
  series,
  range,
  kind,
  format,
}: {
  series: Series[];
  range: RpcUsageRange;
  kind: TrendChartKind;
  format?: ValueFormat;
}) {
  const locale = useLocale();
  // useId() returns values containing `:`, which is awkward in `url(#...)`
  // refs — strip it so the gradient id is a plain identifier.
  const gradientId = useId().replace(/:/g, "");
  const stacked = kind === "area-stacked" || kind === "bar-stacked";

  const { rows, config, max } = useMemo(
    () => buildChartData(series, stacked),
    [series, stacked],
  );
  const pointMarkers = hasSingleBucket(rows.length);

  // A `format` (percent / bytes / ms) supplies its own axis spec; otherwise fall
  // back to the default integer-count axis every existing card relies on.
  const axis = useMemo<AxisSpec>(
    () =>
      format ? format.axis(max) : { ...niceAxis(max), allowDecimals: false },
    [format, max],
  );

  const valueFormatter = useMemo(
    () => (format ? (v: number) => format.format(v, false) : undefined),
    [format],
  );

  const tickFormatter = useMemo(
    () => makeTickFormatter(locale, range),
    [locale, range],
  );

  const tooltipLabelFormatter = useMemo(
    () => makeTooltipLabelFormatter(locale, range),
    [locale, range],
  );

  const grid = (
    <CartesianGrid
      vertical={false}
      stroke="var(--ink-900)"
      strokeOpacity={0.06}
    />
  );
  const xAxis = (
    <XAxis
      dataKey="bucket_start"
      tickLine={false}
      axisLine={false}
      tickMargin={8}
      minTickGap={32}
      tickFormatter={tickFormatter}
    />
  );
  const yAxis = (
    <YAxis
      tickLine={false}
      axisLine={false}
      tickMargin={8}
      width={format?.axisWidth}
      allowDecimals={axis.allowDecimals}
      domain={[0, axis.top]}
      ticks={axis.ticks}
      tickFormatter={
        axis.tickFormat ??
        (format
          ? (v: number) => format.format(v, true)
          : (v: number) => formatCompactNumber(v, locale))
      }
    />
  );
  const tooltip = (
    <ChartTooltip
      cursor={false}
      content={
        <ChartTooltipContent
          indicator="dot"
          labelFormatter={tooltipLabelFormatter}
          valueFormatter={valueFormatter}
        />
      }
    />
  );
  const margin = { left: 0, right: 12, top: 8, bottom: 0 };

  let chart: ReactElement;
  if (kind === "line") {
    chart = (
      <LineChart data={rows} margin={margin}>
        {grid}
        {xAxis}
        {yAxis}
        {tooltip}
        {series.map((s) => (
          <Line
            key={s.key}
            dataKey={s.key}
            type="monotone"
            stroke={`var(--color-${s.key})`}
            strokeWidth={2}
            dot={pointMarkers}
          />
        ))}
      </LineChart>
    );
  } else if (kind === "bar-stacked") {
    chart = (
      <BarChart data={rows} margin={margin}>
        {grid}
        {xAxis}
        {yAxis}
        {tooltip}
        {series.map((s) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            stackId="stack"
            fill={`var(--color-${s.key})`}
            maxBarSize={28}
          />
        ))}
      </BarChart>
    );
  } else {
    chart = (
      <AreaChart data={rows} margin={margin}>
        <defs>
          {series.map((s) => (
            <linearGradient
              key={s.key}
              id={`${gradientId}-${s.key}`}
              x1="0"
              y1="0"
              x2="0"
              y2="1"
            >
              <stop
                offset="5%"
                stopColor={`var(--color-${s.key})`}
                stopOpacity={0.8}
              />
              <stop
                offset="95%"
                stopColor={`var(--color-${s.key})`}
                stopOpacity={0.1}
              />
            </linearGradient>
          ))}
        </defs>
        {grid}
        {xAxis}
        {yAxis}
        {tooltip}
        {series.map((s) => (
          <Area
            key={s.key}
            dataKey={s.key}
            type="monotone"
            stroke={`var(--color-${s.key})`}
            fill={`url(#${gradientId}-${s.key})`}
            stackId={stacked ? "stack" : undefined}
            dot={pointMarkers}
          />
        ))}
      </AreaChart>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <ChartContainer config={config} className={cn("h-72 w-full")}>
        {chart}
      </ChartContainer>
      <UsageLegend series={series} />
    </div>
  );
}

// The legend is rendered outside the chart on purpose: recharts' in-chart
// <Legend> reserves a one-time measured height, so when items wrap to extra
// rows on narrow screens the overflow collides with the X axis. A normal
// flow element below the chart grows naturally and never overlaps.
function UsageLegend({ series }: { series: Series[] }) {
  return (
    <ul className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2">
      {series.map((s, i) => (
        <li key={s.key} className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="size-2 shrink-0 rounded-full"
            style={{ backgroundColor: s.color ?? PALETTE[i % PALETTE.length] }}
          />
          <span className="text-xs text-ink-700">{s.label}</span>
        </li>
      ))}
    </ul>
  );
}

type ChartRow = { bucket_start: string } & Record<string, number | string>;

function buildChartData(
  series: Series[],
  stacked = false,
): {
  rows: ChartRow[];
  config: ChartConfig;
  max: number;
} {
  const byBucket = new Map<string, ChartRow>();

  for (const s of series) {
    for (const point of s.points) {
      const existing = byBucket.get(point.bucket_start);
      if (existing) {
        existing[s.key] = point.value;
      } else {
        byBucket.set(point.bucket_start, {
          bucket_start: point.bucket_start,
          [s.key]: point.value,
        });
      }
    }
  }

  const rows = Array.from(byBucket.values()).sort((a, b) =>
    a.bucket_start < b.bucket_start ? -1 : 1,
  );

  const config: ChartConfig = {};
  series.forEach((s, i) => {
    config[s.key] = {
      label: s.label,
      color: s.color ?? PALETTE[i % PALETTE.length],
    };
  });

  // Axis ceiling. Unstacked: each series is drawn from 0 independently, so the
  // axis fits the tallest individual series (summing would make a small by-method
  // chart as tall as by-network). Stacked: the bands compose upward, so the axis
  // must fit the tallest per-bucket sum instead.
  let max = 0;
  for (const row of rows) {
    if (stacked) {
      let rowSum = 0;
      for (const s of series) {
        const value = row[s.key];
        if (typeof value === "number") rowSum += value;
      }
      if (rowSum > max) max = rowSum;
    } else {
      for (const s of series) {
        const value = row[s.key];
        if (typeof value === "number" && value > max) max = value;
      }
    }
  }

  return { rows, config, max };
}

// Round a raw step up to a "nice" integer interval (1, 2, 5 × 10^n). Counts are
// whole numbers (allowDecimals={false}), so the floor is 1 — never a fractional
// tick like 0.5.
function niceStep(value: number): number {
  if (value <= 1) return 1;
  const base = 10 ** Math.floor(Math.log10(value));
  const f = value / base;
  const nf = f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10;
  return nf * base; // base >= 1 ⇒ always an integer (1, 2, 5, 10, 20, 50, …)
}

// Derive the Y axis ceiling and evenly-spaced integer ticks from the data peak,
// aiming for ~`targetTicks` divisions. The ceiling is the data max rounded up to
// the next whole step, so the top gap stays within one step (typically <15%)
// instead of jumping a whole decade. Baseline stays 0 — this is a filled area
// chart, where the area encodes magnitude and a non-zero floor would distort it.
function niceAxis(
  dataMax: number,
  targetTicks = 5,
): { top: number; ticks: number[] } {
  if (dataMax <= 0) return { top: 1, ticks: [0, 1] };
  const step = niceStep(dataMax / targetTicks);
  const top = Math.ceil(dataMax / step) * step;
  const ticks: number[] = [];
  for (let v = 0; v <= top; v += step) ticks.push(v);
  return { top, ticks };
}

function makeTickFormatter(locale: string, range: RpcUsageRange) {
  const usesHourBuckets = range === "hourly" || range === "daily";
  const fmt = new Intl.DateTimeFormat(
    locale,
    usesHourBuckets
      ? { hour: "2-digit", minute: "2-digit", hour12: false }
      : { month: "2-digit", day: "2-digit" },
  );
  return (value: string) => fmt.format(new Date(value));
}

function makeTooltipLabelFormatter(locale: string, range: RpcUsageRange) {
  const fmt = new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return (value: unknown) => {
    if (typeof value !== "string") return "";
    void range;
    return fmt.format(new Date(value));
  };
}
