"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function VendorMark({
  label,
  compact = false,
}: {
  label: string;
  compact?: boolean;
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-lg bg-brand-soft font-semibold text-brand",
        compact ? "size-7 text-xs" : "size-10 text-sm",
      )}
    >
      {label.slice(0, 2).toUpperCase()}
    </span>
  );
}

export function Section({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="border-t border-table-frame pt-6 first:border-t-0 first:pt-0">
      <div className="mb-6 flex items-start justify-between gap-6">
        <div className="space-y-1">
          <h3 className="text-base font-semibold text-ink-900">{title}</h3>
          {description ? (
            <p className="max-w-prose-narrow text-sm text-ink-500">
              {description}
            </p>
          ) : null}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
