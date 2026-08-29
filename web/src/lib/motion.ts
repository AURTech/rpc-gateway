/**
 * Shared motion presets — the single vocabulary every animated surface in the
 * console draws from. See DESIGN.md §7 for the doctrine these values encode:
 * what moves, how long it takes, and which of the three layers (CSS / Motion /
 * recharts) owns a given effect.
 *
 * **Variants never embed their own `transition`.** A variant-level transition
 * takes precedence over the `transition` prop, which would make the preset
 * impossible to neutralize under reduced motion — so variants describe values
 * only, and the timing is passed alongside via `useMotionPreset().transition()`
 * (src/hooks/use-motion-preset.ts). Consumers that want a snappier dismissal
 * pass `transitionExit` for the exit phase explicitly.
 *
 * This module is deliberately React-free so it stays importable from anywhere;
 * the reduced-motion adapter lives in the hook.
 */

/** ~200ms ease-out — the standard enter for panels, sheets, cards, list items. */
export const transitionEnter = { duration: 0.2, ease: "easeOut" } as const;

/** ~140ms ease-in — exit is faster than enter so dismissals feel snappy. */
export const transitionExit = { duration: 0.14, ease: "easeIn" } as const;

/**
 * Emphasized-decelerate. The third curve, for anything travelling a page-scale
 * distance (route arrival, auth card mount, a count-up settling on its final
 * value). Mirrored as `--ease-emphasized` in globals.css so the CSS-driven and
 * Motion-driven surfaces share one curve.
 *
 * Typed as a mutable tuple because Motion's `Easing` does not accept a readonly
 * one, so `as const` would not assign.
 */
export const easeEmphasized: [number, number, number, number] = [
  0.22, 1, 0.36, 1,
];

/**
 * Async status swap — skeleton ↔ data ↔ empty ↔ error, and the empty-state slot
 * of a detail panel. A plain fade with no travel, so a placeholder never reads
 * as a sibling of the real content. Pair with `AnimatePresence mode="wait"`
 * keyed on the status.
 */
export const emptyDetailVariants = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
} as const;

/** Sheet/drawer slide. Spring matches the app-shell background push-back so the
 * two read as one coordinated motion. Slight, near-critical bounce. */
export const sheetSpring = {
  type: "spring",
  stiffness: 400,
  damping: 38,
} as const;

/** Sheet overlay scrim — a plain quick fade (tween reads cleaner than a spring
 * on opacity). */
export const sheetOverlayTransition = {
  duration: 0.2,
  ease: "easeOut",
} as const;

type SheetSide = "top" | "right" | "bottom" | "left";

/** Off-screen → in-place → off-screen slide variants for a sheet on a given
 * edge. Percentage travel keeps it measurement-free; the spring runs on the
 * transform. */
export function sheetContentVariants(side: SheetSide) {
  const offscreen =
    side === "right"
      ? { x: "100%" }
      : side === "left"
        ? { x: "-100%" }
        : side === "top"
          ? { y: "-100%" }
          : { y: "100%" };
  // Keep units consistent with `offscreen` (percent, not px) so motion
  // interpolates the slide cleanly instead of snapping across unit types.
  return {
    initial: offscreen,
    animate: { x: "0%", y: "0%" },
    exit: offscreen,
  };
}

/** Menu/popover popper content: crisp scale-from-origin + fade. A tween (no
 * bounce) reads cleaner than a spring on a small dropdown; pair with
 * transform-origin = --radix-*-content-transform-origin so it grows from the
 * trigger corner and stays correct through Radix collision flips. */
export const menuContentVariants = {
  initial: { opacity: 0, scale: 0.96 },
  animate: { opacity: 1, scale: 1 },
  exit: { opacity: 0, scale: 0.96 },
} as const;

/** ~140ms ease-out enter for menu popper content. */
export const menuTransition = { duration: 0.14, ease: "easeOut" } as const;

/** Tab/segment active-pill indicator. Small-travel layout slide; slightly
 * crisper than the sheet spring. */
export const pillSpring = {
  type: "spring",
  stiffness: 500,
  damping: 40,
} as const;

/** Copy button icon swap (Copy ↔ Check). Tight scale+fade so the
 * affordance feels mechanical rather than decorative. */
export const iconSwapVariants = {
  initial: { opacity: 0, scale: 0.6 },
  animate: { opacity: 1, scale: 1 },
  exit: { opacity: 0, scale: 0.6 },
} as const;

/** ~150ms — the icon swap's own timing, tighter than a panel enter. */
export const iconSwapTransition = { duration: 0.15, ease: "easeOut" } as const;

/* ===========================================================================
 * Route arrival
 * ======================================================================== */

/** ~280ms — longer than `transitionEnter` because the whole viewport travels. */
export const pageTransition = {
  duration: 0.28,
  ease: easeEmphasized,
} as const;

/**
 * Route arrival. Enter only: the App Router replaces `children` at commit, so
 * there is no outgoing subtree left to animate — see the comment in
 * src/components/layout/page-transition.tsx for why the alternatives were
 * rejected. Navigation reads as "arrival", never "departure".
 */
export const pageVariants = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
} as const;

/* ===========================================================================
 * Collections
 * ======================================================================== */

/** 35ms between siblings — 10 items land in 315ms plus the item's own 200ms. */
export const STAGGER_STEP = 0.035;

/**
 * Stagger depth cap, in items. One data-table viewport's worth. Item `n` beyond
 * this reuses the last delay, so a 200-row infinite list never takes seven
 * seconds to finish appearing. Native table rows use the tighter table-specific
 * timing below; Motion lists continue to use STAGGER_STEP.
 */
export const STAGGER_MAX = 10;

/**
 * Native table rows use CSS rather than Motion so `<tr>` never gains a
 * transform stacking context. These millisecond values are forwarded as CSS
 * custom properties by `TableRow`; keep them aligned with the standard 200ms
 * enter while tightening the list rhythm for dense operational tables.
 */
export const TABLE_ROW_ENTER_MS = 200;
export const TABLE_ROW_STAGGER_MS = 20;

export const listContainerVariants = {
  initial: {},
  animate: {
    transition: { staggerChildren: STAGGER_STEP, delayChildren: 0.02 },
  },
} as const;

export const listItemVariants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -4 },
} as const;

/* ===========================================================================
 * Forms
 * ======================================================================== */

/**
 * Collapsing reveal for form errors and expandable sections. Animating `height`
 * to and from `auto` needs `overflow-hidden` on the element, otherwise the
 * content spills during the collapse.
 */
export const collapseVariants = {
  initial: { height: 0, opacity: 0 },
  animate: { height: "auto", opacity: 1 },
  exit: { height: 0, opacity: 0 },
} as const;

/** Inline table disclosure. Opening has enough time to reveal measured content;
 * closing is quicker, but not so abrupt that the table frame lags behind it.
 * Mirrored by the table spotlight CSS durations in globals.css. */
export const tableDisclosureEnter = {
  duration: 0.28,
  ease: easeEmphasized,
} as const;

export const tableDisclosureExit = {
  duration: 0.18,
  ease: "easeIn",
} as const;

/**
 * Wizard step swap. `custom` carries the direction: +1 when advancing, -1 when
 * going back, so the outgoing step always leaves opposite the incoming one.
 * 24px ≈ half a card gutter — enough to read as directional, short enough not
 * to feel like a carousel.
 */
export const wizardStepVariants = {
  initial: (direction: number) => ({ opacity: 0, x: direction * 24 }),
  animate: { opacity: 1, x: 0 },
  exit: (direction: number) => ({ opacity: 0, x: direction * -24 }),
};

/* ===========================================================================
 * Hover / press
 *
 * Deliberately absent. Hover lift and press feedback are Tailwind `hover:` /
 * `active:` utilities (the `ui/button.tsx` idiom): no JS, no client boundary,
 * and neutralized by the reduced-motion block in globals.css for free. Motion
 * presets for them were tried and removed — nothing needed them, because no
 * hover surface in the console is already a `motion` element.
 * ======================================================================== */

/* ===========================================================================
 * Values
 * ======================================================================== */

/** KPI count-up. Long enough to be legible as a change, short enough that the
 * final value is readable before the eye moves on. */
export const countUpTransition = {
  duration: 0.85,
  ease: easeEmphasized,
} as const;

/* ===========================================================================
 * Charts
 *
 * recharts owns its own animation clock — these are recharts prop values, NOT
 * Motion transitions. Its `isAnimationActive: "auto"` default already resolves
 * `prefers-reduced-motion` internally, so these must never be gated on
 * `useMotionPreset()`; doing so would only disable the tuning, not the
 * animation. Charts already animate at recharts' 1500ms default — this brings
 * them onto the console's ladder.
 * ======================================================================== */

export const CHART_DRAW_MS = 700;
export const CHART_DRAW_EASING = "ease-out" as const;
export const CHART_SERIES_STAGGER_MS = 60;
