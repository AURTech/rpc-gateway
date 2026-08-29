"use client";

import { type HTMLMotionProps, motion } from "motion/react";

import { useMotionPreset } from "@/hooks/use-motion-preset";
import {
  listContainerVariants,
  listItemVariants,
  transitionEnter,
} from "@/lib/motion";

/**
 * Staggered entrance for a collection of `<div>`-based rows or cards.
 *
 * `MotionList` owns the timing and `MotionListItem` owns the travel; Motion
 * propagates the `animate` variant to the items through React context, so the
 * two do not have to be adjacent in the DOM — an item can sit inside whatever
 * wrapper the list already had.
 *
 * Both components render a plain `div` and forward everything else, so they can
 * absorb an existing element rather than add a level: pass the grid or divider
 * classes straight through. Adding a nesting level would break `card-grid-view`
 * (the grid would gain a single child) and `mobile-data-list` (the per-item
 * divider shadow).
 *
 * Not for table rows — a `<tr>` staggers through `TableRow`'s `enterIndex`
 * instead, for the stacking-context reason in DESIGN.md §7.
 */
/**
 * The element to render. `div` covers most lists; `ul`/`li` keep a semantic
 * list valid (a `div` between `ul` and `li` is invalid HTML and would break any
 * `divide-*` rule on the parent), and `section` preserves a labelled region
 * such as the KPI strip.
 */
const LIST_TAGS = {
  div: motion.div,
  ul: motion.ul,
  section: motion.section,
} as const;

const ITEM_TAGS = {
  div: motion.div,
  li: motion.li,
} as const;

export type MotionListProps = HTMLMotionProps<"div"> & {
  as?: keyof typeof LIST_TAGS;
};

export function MotionList({
  as = "div",
  children,
  ...props
}: MotionListProps) {
  const motionPreset = useMotionPreset();
  // Props stay div-typed: every attribute these lists actually pass (className,
  // aria-*, data-*) is shared by all three tags, and a generic signature would
  // only make the union unassignable without buying callers anything.
  const Component = LIST_TAGS[as] as typeof motion.div;

  return (
    <Component
      data-slot="motion-list"
      variants={listContainerVariants}
      initial={motionPreset.initial("initial")}
      animate="animate"
      {...props}
    >
      {children}
    </Component>
  );
}

export type MotionListItemProps = HTMLMotionProps<"div"> & {
  as?: keyof typeof ITEM_TAGS;
};

export function MotionListItem({
  as = "div",
  children,
  ...props
}: MotionListItemProps) {
  const motionPreset = useMotionPreset();
  // See MotionList — same reasoning for the cast.
  const Component = ITEM_TAGS[as] as typeof motion.div;

  return (
    <Component
      data-slot="motion-list-item"
      variants={listItemVariants}
      transition={motionPreset.transition(transitionEnter)}
      {...props}
    >
      {children}
    </Component>
  );
}
