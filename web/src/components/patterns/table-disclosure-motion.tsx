"use client";

import { motion, useIsPresent } from "motion/react";

import { useMotionPreset } from "@/hooks/use-motion-preset";
import {
  collapseVariants,
  tableDisclosureEnter,
  tableDisclosureExit,
} from "@/lib/motion";

/** Shared height + opacity reveal for inline table detail rows. */
export function TableDisclosureMotion({
  children,
}: {
  children: React.ReactNode;
}) {
  const isPresent = useIsPresent();
  const motionPreset = useMotionPreset();

  return (
    <motion.div
      data-slot="table-disclosure-motion"
      className="overflow-hidden"
      variants={collapseVariants}
      initial={motionPreset.initial("initial")}
      animate="animate"
      exit="exit"
      transition={motionPreset.transition(
        isPresent ? tableDisclosureEnter : tableDisclosureExit,
      )}
    >
      {children}
    </motion.div>
  );
}
