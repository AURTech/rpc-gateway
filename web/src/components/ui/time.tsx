import { formatAbsolute, formatAbsoluteFull } from "@/lib/format-time";
import { cn } from "@/lib/utils";

/**
 * Renders an absolute UTC timestamp as a semantic `<time>` element.
 *
 * Pure presentational (no `"use client"`, usable from server or client). It:
 *  - shows the minute-precision absolute value ({@link formatAbsolute}),
 *  - exposes the machine-readable ISO instant via `datetime`,
 *  - reveals full precision + timezone on hover via `title`
 *    ({@link formatAbsoluteFull}) — recovering the seconds the display drops,
 *  - locks digits with `tabular-nums` so timestamps align in columns.
 *
 * `mono` applies the shared monospaced detail-row look (matches the `Mono`
 * primitive); list cells usually inherit font/size/colour from their `td`, so
 * they can pass nothing. `className` always wins, mirroring `Mono`.
 */
export function Time({
  value,
  className,
  mono = false,
}: {
  value: string | null | undefined;
  className?: string;
  mono?: boolean;
}) {
  const base = cn(
    "tabular-nums",
    mono && "font-mono text-md text-ink-700",
    className,
  );

  if (!value) return <span className={base}>—</span>;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return <span className={base}>{value}</span>;

  return (
    <time
      dateTime={d.toISOString()}
      title={formatAbsoluteFull(value) ?? undefined}
      className={base}
    >
      {formatAbsolute(value)}
    </time>
  );
}
