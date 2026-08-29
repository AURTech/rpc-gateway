import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { sheetSpring } from "@/lib/motion";
import { useMotionPreset } from "./use-motion-preset";

/**
 * `useReducedMotion` is mocked rather than driven through a `window.matchMedia`
 * stub because Motion caches the preference in a module-level singleton that is
 * initialised on the first call and never re-read (see the `TODO` in
 * framer-motion's use-reduced-motion.mjs). `vi.resetModules()` can't clear it
 * either — motion-dom is externalised, so Node's ESM loader keeps the instance
 * alive across the reset. Mocking also puts the test at the right level: this
 * hook's contract is "given a preference, produce these helpers", and detecting
 * the preference is Motion's job.
 *
 * The same constraint applies to any later test that needs the reduced-motion
 * branch — mock this hook; do not stub `matchMedia`. (And note Motion queries
 * the bare `"(prefers-reduced-motion)"` feature, not `"…: reduce"`, so a stub
 * matching the long form would silently never fire.)
 */
const { reducedMotion } = vi.hoisted(() => ({
  reducedMotion: { current: null as boolean | null },
}));

vi.mock("motion/react", async (importOriginal) => ({
  ...(await importOriginal<typeof import("motion/react")>()),
  useReducedMotion: () => reducedMotion.current,
}));

beforeEach(() => {
  reducedMotion.current = false;
});

describe("useMotionPreset", () => {
  it("passes transitions and initial values through when motion is allowed", () => {
    const { result } = renderHook(() => useMotionPreset());

    expect(result.current.reduce).toBe(false);
    expect(result.current.transition(sheetSpring)).toBe(sheetSpring);
    expect(result.current.initial({ opacity: 0 })).toEqual({ opacity: 0 });
  });

  it("collapses transitions and drops the mount offset under reduced motion", () => {
    reducedMotion.current = true;

    const { result } = renderHook(() => useMotionPreset());

    expect(result.current.reduce).toBe(true);
    expect(result.current.transition(sheetSpring)).toEqual({ duration: 0 });
    // `false` is Motion's "start at the animate values" — not "no initial".
    expect(result.current.initial({ opacity: 0 })).toBe(false);
  });

  it("treats the server-side null preference as 'animate'", () => {
    // Motion returns null before the media query resolves; animating is the
    // right default, since the reduced-motion CSS layer still applies.
    reducedMotion.current = null;

    const { result } = renderHook(() => useMotionPreset());

    expect(result.current.reduce).toBe(false);
    expect(result.current.transition(sheetSpring)).toBe(sheetSpring);
  });

  it("keeps a stable identity across re-renders", () => {
    const { result, rerender } = renderHook(() => useMotionPreset());
    const first = result.current;

    rerender();

    expect(result.current).toBe(first);
  });
});
