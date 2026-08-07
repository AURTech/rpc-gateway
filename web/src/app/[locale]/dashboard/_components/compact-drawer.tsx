"use client";

import { MoreHorizontalIcon } from "lucide-react";
import { Popover as PopoverPrimitive } from "radix-ui";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Shared primitives for the compact row-expansion drawer.
 *
 * Every list table opens its drawer inside a fixed-height viewport where the
 * drawer is hard-capped at 2 rows (see `TableExpandedRow` in components/ui/table).
 * To honour that without an internal scroll, each drawer shows only a two-line
 * summary (`CompactDrawer` + `DrawerRow`s) and parks everything else behind a
 * floating "details" popover (`DrawerDetailsMenu`) that escapes the cap.
 *
 * Timestamps render via the `<Time>` component (`components/ui/time.tsx`) and
 * its formatters live in `lib/format-time.ts` — no date formatting here.
 */

/** Root of a drawer: two compact rows, vertically centered, never taller than
 *  the 2-row cap enforced by the table cell that wraps it. */
export function CompactDrawer({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col justify-center gap-1.5 px-6 py-2 md:px-8">
      {children}
    </div>
  );
}

/** One line inside the drawer — a flex row that truncates rather than wraps. */
export function DrawerRow({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex min-w-0 items-center gap-2", className)}>
      {children}
    </div>
  );
}

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

/**
 * The "⋯" trigger + floating details panel. Content is portaled so it is free
 * of the drawer's 2-row clip and may scroll internally. Pass `hasAlert` to
 * surface a danger dot on the trigger (e.g. an upstream's last error); pair it
 * with `alertLabel` so the alert is announced to assistive tech — the dot alone
 * is decorative (aria-hidden) and must not be the sole signal of the alert.
 */
export function DrawerDetailsMenu({
  label,
  hasAlert = false,
  alertLabel,
  children,
}: {
  label: string;
  hasAlert?: boolean;
  alertLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <PopoverPrimitive.Root>
      <PopoverPrimitive.Trigger asChild>
        <button
          type="button"
          aria-label={label}
          className="relative inline-flex size-7 shrink-0 items-center justify-center rounded-md text-ink-400 transition-colors hover:bg-ink-wash hover:text-ink-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 data-[state=open]:bg-ink-wash data-[state=open]:text-ink-900"
        >
          <MoreHorizontalIcon className="size-4" aria-hidden />
          {hasAlert ? (
            <>
              <span
                aria-hidden
                className="absolute top-1 right-1 size-1.5 rounded-full bg-danger"
              />
              {alertLabel ? (
                <span className="sr-only">{alertLabel}</span>
              ) : null}
            </>
          ) : null}
        </button>
      </PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          align="end"
          sideOffset={8}
          collisionPadding={12}
          className="z-50 max-h-(--radix-popover-content-available-height) w-80 origin-(--radix-popover-content-transform-origin) overflow-x-hidden overflow-y-auto rounded-xl bg-popover p-3 text-popover-foreground shadow-overlay data-[side=bottom]:slide-in-from-top-2 data-[side=top]:slide-in-from-bottom-2 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95"
        >
          <div className="flex flex-col gap-3">{children}</div>
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
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
