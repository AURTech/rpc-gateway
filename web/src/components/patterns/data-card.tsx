"use client";

import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Mobile list-item card — the row equivalent for narrow viewports where a
 * multi-column table would overflow. Resource-agnostic: callers fill the named
 * slots (icon / title / meta / trailing / actions) for gateways, upstreams,
 * routes, apps, etc.
 *
 * The whole card is tappable (mouse + keyboard) like a table row; nested
 * interactive controls in `actions` / `title` must `stopPropagation` so they
 * don't also trigger the card's `onClick`. Mirrors the table-row hover wash and
 * `data-state="open"` selected styling.
 */
export type DataCardProps = {
  /** Leading visual, e.g. a chain icon. */
  icon?: React.ReactNode;
  title: React.ReactNode;
  /** Secondary line under the title (chain · network, url, …). */
  meta?: React.ReactNode;
  /** Status badges shown before the actions menu. */
  trailing?: React.ReactNode;
  /** The `⋯` actions menu. */
  actions?: React.ReactNode;
  onClick?: () => void;
  /** Highlight while this card's detail drawer is open. */
  selected?: boolean;
  /** Accessible label for the tap-to-open affordance. */
  ariaLabel?: string;
  className?: string;
};

export function DataCard({
  icon,
  title,
  meta,
  trailing,
  actions,
  onClick,
  selected = false,
  ariaLabel,
  className,
}: DataCardProps) {
  const body = (
    <>
      {icon ? <div className="shrink-0">{icon}</div> : null}
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex min-w-0 items-center">{title}</div>
        {meta ? (
          <div className="flex min-w-0 items-center gap-1.5 text-xs text-ink-500">
            {meta}
          </div>
        ) : null}
      </div>
      {trailing ? <div className="shrink-0">{trailing}</div> : null}
      {actions ? <div className="shrink-0">{actions}</div> : null}
    </>
  );

  const base = "flex items-center gap-3 bg-surface px-4 py-3 transition-colors";

  if (!onClick) {
    return <div className={cn(base, className)}>{body}</div>;
  }

  return (
    // biome-ignore lint/a11y/useSemanticElements: a native <button> can't wrap the card's nested interactive controls (actions menu, rename); div+role=button with a keyboard handler is the accessible compromise, mirroring the desktop clickable table row.
    <div
      role="button"
      tabIndex={0}
      aria-label={ariaLabel}
      data-state={selected ? "open" : "closed"}
      onClick={onClick}
      onKeyDown={(e) => {
        // Only the card itself toggles; nested buttons handle their own keys.
        if (e.target !== e.currentTarget) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      className={cn(
        base,
        "cursor-pointer hover:bg-row-hover data-[state=open]:bg-row-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand/40",
        className,
      )}
    >
      {body}
    </div>
  );
}
