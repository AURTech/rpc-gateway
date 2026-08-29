"use client";

import { animate, motion, useMotionValue, useTransform } from "motion/react";
import { useEffect } from "react";

import { useMotionPreset } from "@/hooks/use-motion-preset";
import { countUpTransition } from "@/lib/motion";

export type AnimatedNumberProps = {
  /** The value to settle on. A change re-runs the tween from wherever it is. */
  value: number;
  /**
   * Renders the tweened number. Every frame goes through this, so the label
   * keeps its unit, precision and locale grouping all the way up — a raw count
   * would otherwise flicker between formatted and unformatted text.
   * Memoise it, or hoist it out of the render, so the tween isn't restarted on
   * every parent render.
   */
  format: (value: number) => string;
  className?: string;
};

/**
 * Counts a number up to its value. The interpolation runs on a `MotionValue`
 * rather than React state, so no frame of the tween causes a re-render.
 *
 * The value starts at 0 on both the server and the first client render, which
 * keeps the two in sync — the count-up is a client-only effect that begins
 * afterwards. Under reduced motion it starts at the final value and never
 * tweens.
 */
export function AnimatedNumber({
  value,
  format,
  className,
}: AnimatedNumberProps) {
  const motionPreset = useMotionPreset();
  const current = useMotionValue(motionPreset.reduce ? value : 0);
  const text = useTransform(current, format);

  useEffect(() => {
    if (motionPreset.reduce) {
      current.set(value);
      return;
    }
    const controls = animate(current, value, countUpTransition);
    return () => controls.stop();
  }, [value, current, motionPreset.reduce]);

  return (
    <motion.span data-slot="animated-number" className={className}>
      {text}
    </motion.span>
  );
}
