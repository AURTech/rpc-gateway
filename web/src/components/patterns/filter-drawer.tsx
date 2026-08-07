"use client";

import { Filter } from "lucide-react";
import { useState } from "react";

import { Drawer, DrawerShell, DrawerTrigger } from "@/components/ui/drawer";
import { cn } from "@/lib/utils";

/**
 * Mobile filter surface. On narrow viewports the table's in-header filters are
 * gone, so a toolbar button opens this bottom drawer holding the same filter
 * controls. Drag-to-close + gesture momentum via `vaul`. Resource-agnostic:
 * callers compose {@link FilterMultiGroup} / {@link FilterSingleGroup} (or
 * anything) as children and own the filter state, exactly like the desktop
 * header filters — both views drive one shared state.
 */

const TOOLBAR_TRIGGER_CLASS =
  "inline-flex h-10 items-center gap-1.5 rounded-md bg-surface px-3 text-sm font-medium text-ink-700 shadow-card transition-colors hover:bg-row-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30";

const CHIP_CLASS =
  "inline-flex h-8 items-center rounded-full px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40";

export type FilterDrawerProps = {
  /** Trigger label, e.g. "Filter". */
  label: string;
  /** Drawer heading. */
  title: string;
  /** Count of active filters; surfaced as a badge on the trigger. */
  activeCount?: number;
  /** Clear-all handler + label, shown in the header when any filter is active. */
  onReset?: () => void;
  resetLabel?: string;
  /** Footer close-button label. */
  doneLabel: string;
  children: React.ReactNode;
};

export function FilterDrawer({
  label,
  title,
  activeCount = 0,
  onReset,
  resetLabel,
  doneLabel,
  children,
}: FilterDrawerProps) {
  const [open, setOpen] = useState(false);
  const active = activeCount > 0;

  return (
    <Drawer open={open} onOpenChange={setOpen}>
      <DrawerTrigger asChild>
        <button
          type="button"
          className={cn(TOOLBAR_TRIGGER_CLASS, active && "text-brand")}
        >
          <Filter
            className={cn("size-4", active ? "text-brand" : "text-ink-500")}
            aria-hidden
          />
          {label}
          {active ? (
            <span className="inline-flex min-w-5 items-center justify-center rounded-full bg-brand-soft px-1.5 text-2xs font-semibold text-brand">
              {activeCount}
            </span>
          ) : null}
        </button>
      </DrawerTrigger>
      <DrawerShell
        title={title}
        headerEnd={
          active && onReset ? (
            <button
              type="button"
              onClick={onReset}
              className="text-sm font-medium text-ink-500 transition-colors hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
            >
              {resetLabel}
            </button>
          ) : undefined
        }
        footer={
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="inline-flex h-10 w-full items-center justify-center rounded-md bg-brand text-sm font-semibold text-white shadow-action transition-colors hover:bg-brand-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
          >
            {doneLabel}
          </button>
        }
      >
        <div className="flex flex-col gap-5">{children}</div>
      </DrawerShell>
    </Drawer>
  );
}

/** Labelled multi-select filter group (empty selection = all). */
export function FilterMultiGroup<T extends string>({
  label,
  options,
  optionLabels,
  value,
  onValueChange,
}: {
  label: string;
  options: readonly T[];
  optionLabels: Record<T, string>;
  value: readonly T[];
  onValueChange: (next: readonly T[]) => void;
}) {
  const selected = new Set(value);
  const toggle = (opt: T) => {
    if (selected.has(opt)) onValueChange(value.filter((v) => v !== opt));
    else onValueChange([...value, opt]);
  };
  return (
    <FilterGroup label={label}>
      {options.map((opt) => {
        const on = selected.has(opt);
        return (
          <button
            key={opt}
            type="button"
            aria-pressed={on}
            onClick={() => toggle(opt)}
            className={cn(
              CHIP_CLASS,
              on
                ? "bg-brand-soft text-brand"
                : "bg-ink-wash text-ink-700 hover:bg-stripe",
            )}
          >
            {optionLabels[opt]}
          </button>
        );
      })}
    </FilterGroup>
  );
}

/** Labelled single-select filter group (mutually exclusive choices). */
export function FilterSingleGroup<T extends string>({
  label,
  options,
  optionLabels,
  value,
  onValueChange,
}: {
  label: string;
  options: readonly T[];
  optionLabels: Record<T, string>;
  value: T;
  onValueChange: (next: T) => void;
}) {
  return (
    <FilterGroup label={label}>
      {options.map((opt) => {
        const on = value === opt;
        return (
          <button
            key={opt}
            type="button"
            aria-pressed={on}
            onClick={() => onValueChange(opt)}
            className={cn(
              CHIP_CLASS,
              on
                ? "bg-brand-soft text-brand"
                : "bg-ink-wash text-ink-700 hover:bg-stripe",
            )}
          >
            {optionLabels[opt]}
          </button>
        );
      })}
    </FilterGroup>
  );
}

export function FilterGroup({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-2xs font-semibold tracking-wide text-ink-400 uppercase">
        {label}
      </span>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}
