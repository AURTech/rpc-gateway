/**
 * Shared motion presets — keep micro-animations consistent across the
 * dashboard. Anything beyond these primitives is too much for an admin
 * UI: list staggers and big page transitions are intentionally left out.
 */

/** ~200ms ease-out — standard fade/slide for detail panel + sheet swaps. */
export const transitionEnter = { duration: 0.2, ease: "easeOut" } as const;

/** ~140ms ease-in — exit is faster than enter so dismissals feel snappy. */
export const transitionExit = { duration: 0.14, ease: "easeIn" } as const;

/** Detail panel: subtle horizontal slide + fade. Direction matches the
 * left→right reading order: new selection slides in from the right. */
export const detailPanelVariants = {
  initial: { opacity: 0, x: 12 },
  animate: {
    opacity: 1,
    x: 0,
    transition: transitionEnter,
  },
  exit: {
    opacity: 0,
    x: -8,
    transition: transitionExit,
  },
} as const;

/** Empty-state slot uses the same fade with no horizontal travel so
 * the placeholder doesn't feel like a sibling of the real panels. */
export const emptyDetailVariants = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: transitionEnter },
  exit: { opacity: 0, transition: transitionExit },
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

/** ~140ms ease-out enter for menu popper content. Kept off the variants so the
 * `transition` prop can swap to `{ duration: 0 }` under reduced motion. */
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
  animate: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.15, ease: "easeOut" },
  },
  exit: {
    opacity: 0,
    scale: 0.6,
    transition: { duration: 0.1, ease: "easeIn" },
  },
} as const;
