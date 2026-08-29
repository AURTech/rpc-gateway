import type { ComponentType, ReactNode } from "react";
import { useId } from "react";
import { MotionList, MotionListItem } from "@/components/patterns/motion-list";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { cn } from "@/lib/utils";

type Tone = "brand" | "positive" | "neutral" | "danger";

type DeltaDirection = "up" | "down" | "neutral";

type DeltaSemantic = "good" | "bad" | "neutral";

type KpiDelta = {
  label: string;
  direction: DeltaDirection;
  semantic: DeltaSemantic;
  caption?: string;
};

type KpiSparkline = {
  data: readonly number[];
  tone?: Tone;
};

export type KpiTileProps = {
  label: string;
  value: string;
  /**
   * Tween the number up to `to` instead of rendering `value` statically.
   * The raw number and its formatter travel together so a frame of the tween
   * can never be rendered unformatted.
   *
   * `value` stays required and is what renders on the server, under reduced
   * motion, and whenever `count` is omitted.
   */
  count?: { to: number; format: (value: number) => string };
  unit?: string;
  delta?: KpiDelta;
  caption?: string;
  sparkline?: KpiSparkline;
  icon?: ComponentType<{ className?: string }>;
};

export type KpiStripProps = {
  tiles: readonly KpiTileProps[];
  ariaLabel?: string;
  // Override the default responsive 4-column grid. Overview's redesigned top
  // row stacks 3 tiles vertically beside the apps panel (`grid grid-cols-1`).
  className?: string;
};

export function KpiStrip({ tiles, ariaLabel, className }: KpiStripProps) {
  return (
    // `as="section"` keeps the labelled region; MotionList absorbs the element
    // rather than nesting, so the grid is unchanged. The tiles mount when their
    // query resolves, so the stagger reads as "the numbers arrived" rather than
    // repeating the route-level arrival.
    <MotionList
      as="section"
      aria-label={ariaLabel}
      className={
        className ?? "grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4"
      }
    >
      {tiles.map((tile) => (
        <KpiTile key={tile.label} {...tile} />
      ))}
    </MotionList>
  );
}

function KpiTile({
  label,
  value,
  count,
  unit,
  delta,
  caption,
  sparkline,
  icon: Icon,
}: KpiTileProps) {
  return (
    <MotionListItem className="flex min-h-30 flex-col rounded-xl bg-surface px-4 py-3 shadow-section">
      <div className="flex items-center gap-2">
        {Icon ? <Icon className="size-4 text-ink-400" /> : null}
        <span className="text-sm font-medium text-ink-500">{label}</span>
      </div>
      {sparkline ? (
        <RichBody
          value={value}
          count={count}
          unit={unit}
          delta={delta}
          caption={caption}
          sparkline={sparkline}
        />
      ) : (
        <CompactBody
          value={value}
          count={count}
          unit={unit}
          delta={delta}
          caption={caption}
        />
      )}
    </MotionListItem>
  );
}

function CompactBody({
  value,
  count,
  unit,
  delta,
  caption,
}: Pick<KpiTileProps, "value" | "count" | "unit" | "delta" | "caption">) {
  return (
    <>
      <div className="mt-auto pt-3">
        <Value value={value} count={count} unit={unit} />
      </div>
      {delta || caption ? (
        <div className="mt-2 flex min-w-0 items-center gap-1.5">
          {delta ? (
            <DeltaPill direction={delta.direction} semantic={delta.semantic}>
              {delta.label}
            </DeltaPill>
          ) : null}
          {caption ? (
            <p className="truncate text-xs text-ink-400">{caption}</p>
          ) : null}
        </div>
      ) : null}
    </>
  );
}

function RichBody({
  value,
  count,
  unit,
  delta,
  caption,
  sparkline,
}: Pick<KpiTileProps, "value" | "count" | "unit" | "delta" | "caption"> & {
  sparkline: KpiSparkline;
}) {
  return (
    <div className="mt-auto flex items-end justify-between gap-3 pt-3">
      <div className="flex min-w-0 flex-col gap-1.5">
        <Value value={value} count={count} unit={unit} />
        {delta ? (
          <div className="flex items-center gap-1.5 text-xs">
            <TrendText direction={delta.direction} semantic={delta.semantic}>
              {delta.label}
            </TrendText>
            {delta.caption ? (
              <span className="text-ink-400">{delta.caption}</span>
            ) : null}
          </div>
        ) : null}
        {caption ? (
          <span className="text-xs text-ink-400">{caption}</span>
        ) : null}
      </div>
      <Sparkline
        data={sparkline.data}
        tone={sparkline.tone ?? "brand"}
        className="h-14 w-24 shrink-0"
      />
    </div>
  );
}

function Value({
  value,
  count,
  unit,
}: Pick<KpiTileProps, "value" | "count" | "unit">) {
  return (
    <span className="flex flex-nowrap items-baseline gap-1.5 whitespace-nowrap">
      <span className="text-3xl font-bold leading-none tracking-tight tabular-nums text-ink-900">
        {count ? (
          <AnimatedNumber value={count.to} format={count.format} />
        ) : (
          value
        )}
      </span>
      {unit ? (
        <span className="text-md font-medium text-ink-500">{unit}</span>
      ) : null}
    </span>
  );
}

const SEMANTIC_TEXT: Record<DeltaSemantic, string> = {
  good: "text-positive",
  bad: "text-danger",
  neutral: "text-ink-500",
};

function deltaArrow(direction: DeltaDirection) {
  if (direction === "up") return "↑";
  if (direction === "down") return "↓";
  return null;
}

function DeltaPill({
  direction,
  semantic,
  children,
}: {
  direction: DeltaDirection;
  semantic: DeltaSemantic;
  children: ReactNode;
}) {
  const arrow = deltaArrow(direction);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums",
        semantic === "good" && "bg-positive-soft text-positive",
        semantic === "bad" && "bg-danger-soft text-danger",
        semantic === "neutral" && "bg-ink-wash text-ink-500",
      )}
    >
      {arrow ? (
        <span aria-hidden className="text-2xs leading-none">
          {arrow}
        </span>
      ) : null}
      {children}
    </span>
  );
}

function TrendText({
  direction,
  semantic,
  children,
}: {
  direction: DeltaDirection;
  semantic: DeltaSemantic;
  children: ReactNode;
}) {
  const arrow = deltaArrow(direction);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 font-semibold tabular-nums",
        SEMANTIC_TEXT[semantic],
      )}
    >
      {arrow ? (
        <span aria-hidden className="text-2xs leading-none">
          {arrow}
        </span>
      ) : null}
      {children}
    </span>
  );
}

const SPARKLINE_TEXT: Record<Tone, string> = {
  brand: "text-brand",
  positive: "text-positive",
  neutral: "text-ink-500",
  danger: "text-danger",
};

function Sparkline({
  data,
  tone,
  className,
  title = "Trend",
}: {
  data: readonly number[];
  tone: Tone;
  className?: string;
  title?: string;
}) {
  const rawId = useId();
  const gradientId = `kpi-spark-${rawId.replace(/:/g, "")}`;
  if (data.length === 0) return null;
  const width = 160;
  const height = 48;
  const pad = 4;
  let min = data[0];
  let max = data[0];
  for (const v of data) {
    if (v < min) min = v;
    if (v > max) max = v;
  }
  const range = max - min || 1;
  const step = data.length > 1 ? width / (data.length - 1) : 0;
  const points = data.map((v, i) => {
    const x = i * step;
    const y = height - pad - ((v - min) / range) * (height - 2 * pad);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  const line = points.join(" ");
  const area = `0,${height} ${line} ${width},${height}`;
  return (
    <svg
      aria-hidden
      className={cn("block overflow-visible", SPARKLINE_TEXT[tone], className)}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
    >
      <title>{title}</title>
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.24" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      <polyline points={area} fill={`url(#${gradientId})`} stroke="none" />
      {/* Both stroked lines draw themselves on. `pathLength={1}` normalises the
       * geometry so one dash covers the whole polyline regardless of its real
       * length, which lets a single keyframe animate stroke-dashoffset 1 → 0.
       * Pure CSS, so this file stays a server component. */}
      <polyline
        points={line}
        fill="none"
        stroke="currentColor"
        strokeWidth="3.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.18"
        vectorEffect="non-scaling-stroke"
        pathLength={1}
        strokeDasharray={1}
        className="animate-spark-draw"
      />
      <polyline
        points={line}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
        pathLength={1}
        strokeDasharray={1}
        className="animate-spark-draw"
      />
    </svg>
  );
}
