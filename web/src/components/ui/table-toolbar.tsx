"use client";

import {
  ArrowDown,
  ArrowUp,
  ChevronDown,
  ChevronsUpDown,
  Filter,
  ListFilter,
} from "lucide-react";
import type { ReactNode } from "react";

import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useControllableState } from "@/hooks/use-controllable-state";
import { cn } from "@/lib/utils";

/**
 * In-header / toolbar filter & control widgets for tables. Generic over the
 * option key `<T extends string>`. Each follows the components.build
 * controlled/uncontrolled contract: pass `value` (controlled) or rely on
 * `defaultValue` (uncontrolled); both fire `onValueChange`.
 */

const HEADER_TRIGGER_CLASS =
  "-mx-2 inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40";

const TOOLBAR_TRIGGER_CLASS =
  "inline-flex h-10 items-center gap-1.5 rounded-md bg-surface px-3 text-sm font-medium text-ink-700 shadow-card transition active:scale-95 hover:bg-row-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30";

// Icon-only trigger for the column-visibility control that lives inside the
// last (action) column header. Turns brand-colored when some columns are hidden.
const COLUMNS_TRIGGER_CLASS =
  "inline-flex size-8 items-center justify-center rounded-md text-ink-500 transition active:scale-95 hover:bg-row-hover hover:text-ink-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30";

// Stable empty default for the uncontrolled multi-select — a fresh `[]` literal
// in the param default would be a new reference every render.
const EMPTY_VALUES: readonly never[] = [];

export type MultiHeaderFilterProps<T extends string> = {
  label: string;
  allLabel: string;
  value?: readonly T[];
  defaultValue?: readonly T[];
  onValueChange?: (next: readonly T[]) => void;
  options: readonly T[];
  optionLabels: Record<T, string>;
  allContent?: ReactNode;
  renderOption?: (option: T) => ReactNode;
};

/**
 * Multi-select in-header filter. Trigger label collapses to the single
 * selection when one is on, or "{label} · {count}" when several. Empty
 * selection means "all".
 */
function MultiHeaderFilter<T extends string>({
  label,
  allLabel,
  value,
  defaultValue = EMPTY_VALUES,
  onValueChange,
  options,
  optionLabels,
  allContent,
  renderOption,
}: MultiHeaderFilterProps<T>) {
  const [values, setValues] = useControllableState<readonly T[]>({
    value,
    defaultValue,
    onChange: onValueChange,
  });
  const active = values.length > 0;
  const triggerText =
    values.length === 0
      ? label
      : values.length === 1
        ? optionLabels[values[0] as T]
        : `${label} · ${values.length}`;
  const selected = new Set(values);

  const toggle = (opt: T) => {
    if (selected.has(opt)) setValues(values.filter((v) => v !== opt));
    else setValues([...values, opt]);
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(
            HEADER_TRIGGER_CLASS,
            active ? "text-brand" : "text-ink-500 hover:text-ink-900",
          )}
        >
          {triggerText}
          <ChevronDown
            className={cn("size-3", active ? "text-brand" : "text-ink-400")}
            aria-hidden
          />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-44">
        {/* "All X" pseudo-option — ticked iff nothing individual is selected.
         * Clicking it when unticked clears the selection. */}
        <DropdownMenuCheckboxItem
          checked={!active}
          onSelect={(e) => e.preventDefault()}
          onCheckedChange={(next) => {
            if (next) setValues([]);
          }}
        >
          {allContent ?? allLabel}
        </DropdownMenuCheckboxItem>
        {options.map((opt) => (
          <DropdownMenuCheckboxItem
            key={opt}
            checked={selected.has(opt)}
            // Keep the menu open so the user can multi-pick.
            onSelect={(e) => e.preventDefault()}
            onCheckedChange={() => toggle(opt)}
          >
            {renderOption ? renderOption(opt) : optionLabels[opt]}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export type HeaderFilterProps<T extends string> = {
  label: string;
  value?: T;
  defaultValue?: T;
  onValueChange?: (next: T) => void;
  options: readonly T[];
  optionLabels: Record<T, string>;
  /** Sentinel value meaning "no filter"; the trigger shows `label` when active value equals it. */
  allValue?: T;
};

/** Single-select in-header filter (mutually exclusive choices). */
function HeaderFilter<T extends string>({
  label,
  value,
  defaultValue,
  onValueChange,
  options,
  optionLabels,
  allValue = "all" as T,
}: HeaderFilterProps<T>) {
  const [selectedValue, setSelectedValue] = useControllableState<T>({
    value,
    defaultValue: defaultValue ?? allValue,
    onChange: onValueChange,
  });
  const active = selectedValue !== allValue;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(
            HEADER_TRIGGER_CLASS,
            active ? "text-brand" : "text-ink-500 hover:text-ink-900",
          )}
        >
          {active ? optionLabels[selectedValue] : label}
          <ChevronDown
            className={cn("size-3", active ? "text-brand" : "text-ink-400")}
            aria-hidden
          />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-44">
        <DropdownMenuRadioGroup
          value={selectedValue}
          onValueChange={(v) => setSelectedValue(v as T)}
        >
          {options.map((opt) => (
            <DropdownMenuRadioItem key={opt} value={opt}>
              {optionLabels[opt]}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * Toolbar-styled single-select filter — same controlled/uncontrolled contract
 * as {@link HeaderFilter}, but wears the `TOOLBAR_TRIGGER_CLASS` (h-10 surface
 * pill) so it sits inline next to the search box / "New …" action rather than
 * inside a table header cell. Trigger shows the active selection, or `label`
 * when the value equals `allValue`. `triggerClassName` lets a page restyle the
 * trigger (e.g. a sunken ink-wash chip) while keeping the dropdown behavior.
 */
function ToolbarFilter<T extends string>({
  label,
  value,
  defaultValue,
  onValueChange,
  options,
  optionLabels,
  allValue = "all" as T,
  triggerClassName,
}: HeaderFilterProps<T> & { triggerClassName?: string }) {
  const [selectedValue, setSelectedValue] = useControllableState<T>({
    value,
    defaultValue: defaultValue ?? allValue,
    onChange: onValueChange,
  });
  const active = selectedValue !== allValue;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(
            TOOLBAR_TRIGGER_CLASS,
            triggerClassName,
            active && "text-brand",
          )}
        >
          {active ? optionLabels[selectedValue] : label}
          <ChevronDown
            className={cn("size-3", active ? "text-brand" : "text-ink-400")}
            aria-hidden
          />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-44">
        <DropdownMenuRadioGroup
          value={selectedValue}
          onValueChange={(v) => setSelectedValue(v as T)}
        >
          {options.map((opt) => (
            <DropdownMenuRadioItem key={opt} value={opt}>
              {optionLabels[opt]}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export type ColumnsToggleProps<T extends string> = {
  label: string;
  columns: readonly T[];
  labels: Record<T, string>;
  value?: Set<T>;
  defaultValue?: Set<T>;
  onValueChange?: (next: Set<T>) => void;
};

/**
 * Column-visibility control, rendered as an icon-only filter button inside the
 * last (action) column header. Emits the full next Set; enforcing a minimum of
 * one visible column is the consumer's job (e.g. the table controller).
 */
function ColumnsToggle<T extends string>({
  label,
  columns,
  labels,
  value,
  defaultValue,
  onValueChange,
}: ColumnsToggleProps<T>) {
  const [visible, setVisible] = useControllableState<Set<T>>({
    value,
    defaultValue: defaultValue ?? new Set(columns),
    onChange: onValueChange,
  });
  const active = visible.size < columns.length;
  const toggle = (col: T, next: boolean) => {
    const updated = new Set(visible);
    if (next) updated.add(col);
    else updated.delete(col);
    setVisible(updated);
  };
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={label}
          title={label}
          className={cn(COLUMNS_TRIGGER_CLASS, active && "text-brand")}
        >
          <Filter className="size-4" aria-hidden />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-40">
        {columns.map((col) => (
          <DropdownMenuCheckboxItem
            key={col}
            checked={visible.has(col)}
            onSelect={(e) => e.preventDefault()}
            onCheckedChange={(next) => toggle(col, next)}
          >
            {labels[col]}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export type SortPickerProps<T extends string> = {
  label: string;
  options: { value: T; label: string }[];
  value?: T;
  defaultValue?: T;
  onValueChange?: (next: T) => void;
};

/** Toolbar dropdown: single-select sort picker (value is typically a `field-order` slug). */
function SortPicker<T extends string>({
  label,
  options,
  value,
  defaultValue,
  onValueChange,
}: SortPickerProps<T>) {
  const [selectedValue, setSelectedValue] = useControllableState<T>({
    value,
    defaultValue: defaultValue ?? (options[0]?.value as T),
    onChange: onValueChange,
  });
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" className={TOOLBAR_TRIGGER_CLASS}>
          <ListFilter className="size-4 text-ink-500" aria-hidden />
          {label}
          <ChevronDown className="size-3 text-ink-400" aria-hidden />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-52">
        <DropdownMenuRadioGroup
          value={selectedValue}
          onValueChange={(v) => setSelectedValue(v as T)}
        >
          {options.map((opt) => (
            <DropdownMenuRadioItem key={opt.value} value={opt.value}>
              {opt.label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export type SortOrder = "asc" | "desc";

export type SortableHeaderProps = {
  label: string;
  /** True when this column is the table's active sort key. */
  active: boolean;
  /** Current direction; only meaningful while `active`. */
  order: SortOrder;
  /** Fired on click; the consumer computes and applies the next sort. */
  onToggle: () => void;
  /** Tooltip/aria when the next click sorts ascending. */
  ascLabel: string;
  /** Tooltip/aria when the next click sorts descending. */
  descLabel: string;
};

/**
 * Clickable in-header sort toggle. Inactive columns show a muted two-way
 * chevron and sort descending on first click; the active column shows a
 * directional arrow and flips between asc/desc. The consumer owns the sort
 * state, so this only emits `onToggle`.
 */
function SortableHeader({
  label,
  active,
  order,
  onToggle,
  ascLabel,
  descLabel,
}: SortableHeaderProps) {
  // A click on an inactive column starts at desc; on the active column it
  // flips direction. The tooltip/aria describes that next action.
  const nextOrder: SortOrder = active && order === "desc" ? "asc" : "desc";
  const actionLabel = nextOrder === "asc" ? ascLabel : descLabel;
  const Icon = !active ? ChevronsUpDown : order === "asc" ? ArrowUp : ArrowDown;
  return (
    <button
      type="button"
      onClick={onToggle}
      title={actionLabel}
      aria-label={actionLabel}
      className={cn(
        HEADER_TRIGGER_CLASS,
        active ? "text-brand" : "text-ink-500 hover:text-ink-900",
      )}
    >
      {label}
      <Icon
        className={cn("size-3", active ? "text-brand" : "text-ink-400")}
        aria-hidden
      />
    </button>
  );
}

export {
  MultiHeaderFilter,
  HeaderFilter,
  ToolbarFilter,
  ColumnsToggle,
  SortPicker,
  SortableHeader,
  TOOLBAR_TRIGGER_CLASS,
};
