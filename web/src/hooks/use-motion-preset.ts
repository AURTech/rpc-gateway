"use client";

import { type Transition, useReducedMotion } from "motion/react";
import { useMemo } from "react";

/** One frame is still a frame; zero duration is what "no animation" means. */
const INSTANT: Transition = { duration: 0 };

export interface MotionPreset {
  /**
   * True when the user asked for reduced motion. An escape hatch for cases the
   * two helpers below don't cover (e.g. skipping a `layoutId` entirely); prefer
   * `transition()` / `initial()` so the intent stays declarative.
   */
  reduce: boolean;
  /**
   * Collapse a transition to a single frame. Final values are unchanged, so the
   * element still ends up exactly where it would have — it just gets there
   * without travelling.
   */
  transition: (transition: Transition) => Transition;
  /**
   * Drop the mount offset. Motion reads `initial={false}` as "start at the
   * animate values", which is what a reduced-motion mount should look like:
   * present immediately, no fade or slide in from elsewhere.
   */
  initial: <T>(initial: T) => T | false;
}

/**
 * Reduced-motion adapter for every `motion/react` call site — layer 2 of the
 * three-layer contract in DESIGN.md §7 (layer 1 is the `prefers-reduced-motion`
 * block in globals.css, which JS-driven animations never see; layer 3 is
 * recharts resolving the media query itself).
 *
 * Exists because the raw `reduce ? { duration: 0 } : spring` branch was about
 * to be copied into ~30 components. Deliberately returns an object rather than
 * a tuple so destructuring stays optional — `const motionPreset = …` reads
 * fine at a call site that already has next-intl's `t` in scope.
 */
export function useMotionPreset(): MotionPreset {
  const reduce = useReducedMotion() ?? false;

  return useMemo(
    () => ({
      reduce,
      transition: (transition: Transition) => (reduce ? INSTANT : transition),
      initial: <T>(initial: T) => (reduce ? false : initial),
    }),
    [reduce],
  );
}
