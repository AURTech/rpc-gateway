"use client";

import { motion } from "motion/react";
import { type KeyboardEvent, type ReactNode, useId, useRef } from "react";

import { useMotionPreset } from "@/hooks/use-motion-preset";
import { pillSpring } from "@/lib/motion";
import { cn } from "@/lib/utils";

export type TabOption<T extends string> = {
  value: T;
  label: string;
};

// Two scales share one visual: `sm` (default) is the compact in-card control
// (time-range switches); `lg` is a page-level tab bar that sits comfortably
// above a toolbar of `h-9` controls.
export type TabSize = "sm" | "lg";

// Two visuals share the same behaviour/ARIA:
//   • "pill"      — sliding filled pill on an `ink-wash` track (default). The
//                   compact in-card control; `size` tunes its scale.
//   • "underline" — left-aligned labels over a full-width bottom divider, with
//                   a sliding brand underline on the active tab. A page-level
//                   section nav that visually binds to the content below it.
export type TabVariant = "pill" | "underline";

// `w-fit` keeps the pill track sized to its labels even inside a flex column,
// where an `inline-flex` element would otherwise be blockified and stretched to
// the full container width (its background then spanning the whole row).
const TRACK_PILL = "inline-flex w-fit items-center rounded-full bg-ink-wash";

// Full width so the divider spans the container; labels sit flush-left.
const TRACK_UNDERLINE = "flex w-full items-center border-b border-table-frame";

const TRACK_SIZE: Record<TabSize, string> = {
  sm: "gap-1 p-1",
  lg: "gap-1.5 p-1",
};

const TRACK_UNDERLINE_SIZE: Record<TabSize, string> = {
  sm: "gap-6",
  lg: "gap-8 pl-1",
};

const ITEM_SIZE: Record<TabSize, string> = {
  sm: "px-3 py-1 text-xs",
  lg: "px-4 py-2 text-sm",
};

const ITEM_UNDERLINE_SIZE: Record<TabSize, string> = {
  sm: "px-0.5 pb-3 text-sm",
  lg: "px-0 pt-1 pb-3.5 text-base",
};

function itemClass(active: boolean, variant: TabVariant, size: TabSize) {
  if (variant === "underline") {
    return cn(
      "relative font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60",
      ITEM_UNDERLINE_SIZE[size],
      active ? "text-ink-900" : "text-ink-500 hover:text-ink-700",
    );
  }
  return cn(
    "relative rounded-full font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60",
    ITEM_SIZE[size],
    active ? "text-ink-900" : "text-ink-500 hover:text-ink-700",
  );
}

// A controlled pill switcher with one shared visual (a sliding active pill) and
// two ARIA personalities:
//   • mode="tab"        — a tablist navigating content panels (Usage page).
//   • mode="segmented"  — a radiogroup picking one value of a filter/toggle
//                         (time-range switches). It looks like an iOS segmented
//                         control; "segmented control" is a UI pattern, so the
//                         accessible role is the standard radiogroup/radio.
// Both modes share roving-tabindex keyboard nav: ←/→ (and ↑/↓) cycle, Home/End
// jump to the ends, focus follows, and the move activates immediately.
//
// The two modes render as separate static-role branches on purpose: a dynamic
// `role={cond ? ... : ...}` defeats the a11y linter's static analysis, so each
// branch spells its roles out as literals.
export function Tabs<T extends string>({
  mode,
  value,
  onChange,
  options,
  ariaLabel,
  idBase,
  panelIdForValue,
  size = "sm",
  variant = "pill",
  disabled = false,
}: {
  mode: "tab" | "segmented";
  value: T;
  onChange: (next: T) => void;
  options: readonly TabOption<T>[];
  ariaLabel: string;
  // Only used in tab mode: gives each tab a stable `id` and points
  // `aria-controls` at the caller's `${idBase}-panel` tabpanel.
  idBase?: string;
  // Use when each option keeps its own mounted panel instead of sharing the
  // default `${idBase}-panel` content region.
  panelIdForValue?: (value: T) => string;
  // Visual scale; only applies to the pill variant.
  size?: TabSize;
  // Visual style; defaults to the sliding pill.
  variant?: TabVariant;
  // Disables every option (e.g. while a form that owns the value is saving).
  disabled?: boolean;
}) {
  const trackClass =
    variant === "underline"
      ? cn(TRACK_UNDERLINE, TRACK_UNDERLINE_SIZE[size])
      : cn(TRACK_PILL, TRACK_SIZE[size]);
  // Unique per instance so the sliding pill (shared `layoutId`) never animates
  // across two separate switchers that happen to render on the same page.
  const layoutId = useId();
  const motionPreset = useMotionPreset();

  // Hold each option's button so keyboard navigation can move focus (roving
  // tabindex) without reaching into the DOM by selector.
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const setRef = (index: number) => (el: HTMLButtonElement | null) => {
    itemRefs.current[index] = el;
  };

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const count = options.length;
    const current = options.findIndex((o) => o.value === value);
    let target: number;
    switch (event.key) {
      case "ArrowRight":
      case "ArrowDown":
        target = (current + 1) % count;
        break;
      case "ArrowLeft":
      case "ArrowUp":
        target = (current - 1 + count) % count;
        break;
      case "Home":
        target = 0;
        break;
      case "End":
        target = count - 1;
        break;
      default:
        return;
    }
    event.preventDefault();
    const next = options[target];
    if (next.value !== value) onChange(next.value);
    itemRefs.current[target]?.focus();
  }

  // Shared item interior: the sliding active indicator + the label. The
  // indicator's shape follows the variant — a filled pill behind the label, or
  // a brand underline pinned to the track's bottom divider.
  function pill(active: boolean, label: string): ReactNode {
    const indicatorClass =
      variant === "underline"
        ? "absolute inset-x-0 -bottom-px h-0.5 rounded-full bg-brand"
        : "absolute inset-0 rounded-full bg-surface shadow-section";
    return (
      <>
        {active && (
          <motion.span
            aria-hidden
            layoutId={layoutId}
            className={indicatorClass}
            transition={motionPreset.transition(pillSpring)}
          />
        )}
        <span className="relative z-10">{label}</span>
      </>
    );
  }

  if (mode === "tab") {
    return (
      <div
        role="tablist"
        aria-label={ariaLabel}
        onKeyDown={onKeyDown}
        className={trackClass}
      >
        {options.map((option, index) => {
          const active = option.value === value;
          return (
            <button
              key={option.value}
              ref={setRef(index)}
              type="button"
              role="tab"
              aria-selected={active}
              tabIndex={active ? 0 : -1}
              disabled={disabled}
              id={idBase ? `${idBase}-${option.value}` : undefined}
              aria-controls={
                panelIdForValue
                  ? panelIdForValue(option.value)
                  : idBase
                    ? `${idBase}-panel`
                    : undefined
              }
              onClick={() => onChange(option.value)}
              className={itemClass(active, variant, size)}
            >
              {pill(active, option.label)}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
      className={trackClass}
    >
      {options.map((option, index) => {
        const active = option.value === value;
        return (
          // biome-ignore lint/a11y/useSemanticElements: pill-styled segmented control can't use a native <input type="radio">; button + role="radio" gives the equivalent single-select semantics with the custom visual.
          <button
            key={option.value}
            ref={setRef(index)}
            type="button"
            role="radio"
            aria-checked={active}
            tabIndex={active ? 0 : -1}
            disabled={disabled}
            onClick={() => onChange(option.value)}
            className={itemClass(active, variant, size)}
          >
            {pill(active, option.label)}
          </button>
        );
      })}
    </div>
  );
}
