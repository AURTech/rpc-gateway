"use client";

import { type HTMLMotionProps, motion } from "motion/react";

import { useMotionPreset } from "@/hooks/use-motion-preset";
import { emptyDetailVariants, transitionEnter } from "@/lib/motion";

export type StatusFadeProps = HTMLMotionProps<"div">;

/**
 * Fades an async status panel — empty, filtered-empty, or error — in on mount.
 *
 * Enter only, and deliberately not an `AnimatePresence mode="wait"` crossfade
 * against the skeleton. Waiting for the skeleton to exit would insert a blank
 * gap ahead of the content and make the load *feel* longer, which DESIGN.md
 * §7's No-Blocking Rule rules out. The skeleton-to-data path needs no crossfade
 * either: `MotionList` already staggers the arriving cards.
 *
 * Renders a plain div and forwards everything, so it replaces the wrapper a
 * status panel already had rather than nesting inside it.
 */
export function StatusFade({ children, ...props }: StatusFadeProps) {
  const motionPreset = useMotionPreset();

  return (
    <motion.div
      data-slot="status-fade"
      variants={emptyDetailVariants}
      initial={motionPreset.initial("initial")}
      animate="animate"
      transition={motionPreset.transition(transitionEnter)}
      {...props}
    >
      {children}
    </motion.div>
  );
}
