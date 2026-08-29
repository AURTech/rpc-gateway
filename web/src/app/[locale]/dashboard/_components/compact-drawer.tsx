"use client";

import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Shared primitives for compact resource details and actions.
 *
 * Timestamps render via the `<Time>` component (`components/ui/time.tsx`) and
 * its formatters live in `lib/format-time.ts` — no date formatting here.
 */

/** Quiet square icon button — copy / edit / commit affordances. */
export function IconButton({
  ariaLabel,
  children,
  onClick,
  disabled,
  tone = "default",
  className,
}: {
  ariaLabel: string;
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  tone?: "default" | "brand";
  className?: string;
}) {
  return (
    <button
      type="button"
      aria-label={ariaLabel}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "inline-flex size-8 shrink-0 items-center justify-center rounded-md transition active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-page-bg disabled:cursor-not-allowed disabled:opacity-60 disabled:active:scale-100",
        tone === "brand"
          ? "bg-brand text-white shadow-action hover:bg-brand-hover"
          : "text-ink-400 hover:bg-ink-wash hover:text-brand",
        className,
      )}
    >
      {children}
    </button>
  );
}

/** Monospaced value cell used across drawers and detail rows. */
export function Mono({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn("font-mono text-md tabular-nums text-ink-700", className)}
    >
      {children}
    </span>
  );
}

/** Labelled group of detail rows inside the details popover. */
export function DetailSection({
  title,
  children,
}: {
  title?: string;
  children: React.ReactNode;
}) {
  // Titleless (preferred): the group is delineated by whitespace alone — the
  // parent stack's gap separates groups, no heading text needed.
  if (!title) return <DetailGrid>{children}</DetailGrid>;
  return (
    <div className="flex flex-col gap-1.5">
      <span className="px-1 text-xs font-semibold tracking-wide text-ink-400 uppercase">
        {title}
      </span>
      <DetailGrid>{children}</DetailGrid>
    </div>
  );
}

/** Plain vertical stack of `DetailRow`s — no fill, no card, no dividers. */
export function DetailGrid({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={cn("flex flex-col", className)}>{children}</div>;
}

/** Label / value line: label flushed left, value flushed right (two-end
 *  alignment). Borderless — rows read against the surface, grouped by
 *  `DetailSection`'s heading. */
export function DetailRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 px-1 py-1.5">
      <span className="shrink-0 text-sm font-medium text-ink-500">{label}</span>
      <div className="flex min-w-0 items-center justify-end gap-1.5 text-right">
        {children}
      </div>
    </div>
  );
}
