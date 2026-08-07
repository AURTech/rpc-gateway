"use client";

import { format, startOfDay, startOfMonth, subDays } from "date-fns";
import { CalendarDays } from "lucide-react";
import type { DateRange } from "react-day-picker";

import { Calendar } from "@/components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { TOOLBAR_TRIGGER_CLASS } from "@/components/ui/table-toolbar";
import { cn } from "@/lib/utils";

type DateRangeValue = DateRange | undefined;

/** Quick-range presets, in display order. Each resolves to a `{from,to}` window
 *  on the day it is clicked; `to` defaults to today unless noted. */
const PRESETS = [
  { key: "today", range: (now: Date) => ({ from: now, to: now }) },
  {
    key: "last7Days",
    range: (now: Date) => ({ from: subDays(now, 6), to: now }),
  },
  {
    key: "last28Days",
    range: (now: Date) => ({ from: subDays(now, 27), to: now }),
  },
  {
    key: "thisMonth",
    range: (now: Date) => ({ from: startOfMonth(now), to: now }),
  },
] as const;

type PresetKey = (typeof PRESETS)[number]["key"];

export type DateRangeFilterLabels = {
  /** Trigger text shown when no range is selected. */
  label: string;
  /** Heading above the preset column. */
  presetsHeader: string;
  /** Per-preset labels keyed by preset id. */
  presets: Record<PresetKey, string>;
  clear: string;
};

function formatRange(value: DateRange): string {
  const from = value.from ? format(value.from, "MMM d") : "…";
  if (!value.to || value.from?.getTime() === value.to.getTime()) return from;
  return `${from} – ${format(value.to, "MMM d")}`;
}

/**
 * Shared panel body — a vertical preset rail on the left and a range calendar on
 * the right, mirroring the common date-range-picker layout. Reused by the
 * desktop toolbar popover and the mobile filter drawer.
 */
function DateRangePanel({
  value,
  onChange,
  labels,
}: {
  value: DateRangeValue;
  onChange: (next: DateRangeValue) => void;
  labels: DateRangeFilterLabels;
}) {
  const applyPreset = (key: PresetKey) => {
    const preset = PRESETS.find((p) => p.key === key);
    if (!preset) return;
    const { from, to } = preset.range(startOfDay(new Date()));
    onChange({ from: startOfDay(from), to: startOfDay(to) });
  };

  return (
    <div className="flex">
      <div className="flex w-32 flex-col gap-0.5 border-r border-ink-wash pr-2">
        <span className="px-3 py-1 text-2xs font-semibold uppercase tracking-wide text-ink-400">
          {labels.presetsHeader}
        </span>
        {PRESETS.map((preset) => (
          <button
            key={preset.key}
            type="button"
            onClick={() => applyPreset(preset.key)}
            className="rounded-md px-3 py-1.5 text-left text-sm text-ink-700 transition-colors hover:bg-row-hover"
          >
            {labels.presets[preset.key]}
          </button>
        ))}
      </div>
      <div className="flex flex-col">
        <Calendar
          mode="range"
          numberOfMonths={1}
          selected={value}
          onSelect={onChange}
          autoFocus
        />
        <button
          type="button"
          onClick={() => onChange(undefined)}
          disabled={!value?.from}
          className="mr-3 mb-2 self-end rounded-md px-3 py-1 text-xs font-medium text-ink-500 transition-colors hover:text-ink-900 disabled:opacity-40"
        >
          {labels.clear}
        </button>
      </div>
    </div>
  );
}

/**
 * Desktop toolbar control: a surface pill (matching {@link TOOLBAR_TRIGGER_CLASS})
 * that opens the range {@link DateRangePanel} in a popover. Turns brand-colored
 * and shows the selected window once a range is picked.
 */
function DateRangeFilter({
  value,
  onChange,
  labels,
}: {
  value: DateRangeValue;
  onChange: (next: DateRangeValue) => void;
  labels: DateRangeFilterLabels;
}) {
  const active = Boolean(value?.from);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(TOOLBAR_TRIGGER_CLASS, active && "text-brand")}
        >
          <CalendarDays
            className={cn("size-4", active ? "text-brand" : "text-ink-500")}
            aria-hidden
          />
          {active && value ? formatRange(value) : labels.label}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto p-2">
        <DateRangePanel value={value} onChange={onChange} labels={labels} />
      </PopoverContent>
    </Popover>
  );
}

/**
 * In-header variant of {@link DateRangeFilter}, sized to sit inside a table
 * column header next to a {@link SortableHeader} (mirrors the header filter
 * triggers in table-toolbar). Shows just the calendar glyph until a range is
 * picked, then turns brand-colored and appends the selected window. Opens the
 * same {@link DateRangePanel}.
 */
function HeaderDateFilter({
  value,
  onChange,
  labels,
}: {
  value: DateRangeValue;
  onChange: (next: DateRangeValue) => void;
  labels: DateRangeFilterLabels;
}) {
  const active = Boolean(value?.from);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={labels.label}
          title={labels.label}
          className={cn(
            "-mx-1 inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40",
            active ? "text-brand" : "text-ink-400 hover:text-ink-900",
          )}
        >
          <CalendarDays className="size-3.5" aria-hidden />
          {active && value ? formatRange(value) : null}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto p-2">
        <DateRangePanel value={value} onChange={onChange} labels={labels} />
      </PopoverContent>
    </Popover>
  );
}

export { DateRangeFilter, DateRangePanel, HeaderDateFilter };
