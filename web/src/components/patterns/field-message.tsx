"use client";

import { AnimatePresence, motion } from "motion/react";
import type { ReactNode } from "react";

import { useMotionPreset } from "@/hooks/use-motion-preset";
import { collapseVariants, transitionEnter } from "@/lib/motion";

export type FieldMessageProps = {
  /** Identifies which message is showing; a change swaps with a collapse. */
  messageKey: string;
  /** Wired to the control's `aria-describedby`; must survive verbatim. */
  id?: string;
  /** `field-error` or `field-hint`, kept as-is so styling and tests still match. */
  slot: "field-error" | "field-hint";
  className: string;
  children: ReactNode;
};

/**
 * Collapsing reveal for a field's hint or error.
 *
 * Split out of `form-field.tsx` so `Field` stays a server component: only this
 * one paragraph needs the client boundary, and `Field` is otherwise pure
 * markup used by every form in the console.
 *
 * `overflow-hidden` is on the collapsing wrapper rather than the paragraph, so
 * the text is clipped by the animating height instead of spilling past it.
 * The `id` and `data-slot` land on the paragraph, unchanged from the static
 * markup — `aria-describedby` points at the former and the field tests query
 * the latter.
 */
export function FieldMessage({
  messageKey,
  id,
  slot,
  className,
  children,
}: FieldMessageProps) {
  const motionPreset = useMotionPreset();

  return (
    <AnimatePresence initial={false} mode="wait">
      <motion.div
        key={messageKey}
        className="overflow-hidden"
        variants={collapseVariants}
        initial={motionPreset.initial("initial")}
        animate="animate"
        exit="exit"
        transition={motionPreset.transition(transitionEnter)}
      >
        <p id={id} data-slot={slot} className={className}>
          {children}
        </p>
      </motion.div>
    </AnimatePresence>
  );
}
