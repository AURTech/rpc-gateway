"use client";

import { AnimatePresence, motion } from "motion/react";
import type { ReactNode } from "react";

import { useMotionPreset } from "@/hooks/use-motion-preset";
import { iconSwapTransition, iconSwapVariants } from "@/lib/motion";
import { cn } from "@/lib/utils";

export type SwapLabelProps = {
  /** Identifies the current label; a change crossfades to the new one. */
  swapKey: string;
  className?: string;
  children: ReactNode;
};

/**
 * Crossfades a button's label between states — "Save" ↔ "Saving…", or a label
 * and its spinner.
 *
 * `mode="wait"` because the two labels share the button's line box: overlapping
 * them would stack the text on itself. The exit is 100ms, so nothing about the
 * click feels delayed.
 *
 * Uses the icon-swap preset rather than a fade: a small scale keeps the change
 * legible at button size, where a pure opacity crossfade barely registers.
 */
export function SwapLabel({ swapKey, className, children }: SwapLabelProps) {
  const motionPreset = useMotionPreset();

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.span
        key={swapKey}
        data-slot="swap-label"
        className={cn("inline-flex items-center gap-2", className)}
        variants={iconSwapVariants}
        initial={motionPreset.initial("initial")}
        animate="animate"
        exit="exit"
        transition={motionPreset.transition(iconSwapTransition)}
      >
        {children}
      </motion.span>
    </AnimatePresence>
  );
}
