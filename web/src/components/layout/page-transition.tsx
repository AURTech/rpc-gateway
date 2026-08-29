"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";

import { useMotionPreset } from "@/hooks/use-motion-preset";
import { usePathname } from "@/i18n/navigation";
import { pageTransition, pageVariants } from "@/lib/motion";

/**
 * Plays a single enter animation each time the route changes. Keyed on the
 * locale-stripped pathname, so React discards the previous subtree and Motion
 * runs `initial → animate` on the fresh one.
 *
 * **Enter only, by design.** An exit animation would need the outgoing page to
 * stay mounted, but the App Router replaces `children` at commit. The only
 * known workaround is to cache and re-provide Next's private
 * `LayoutRouterContext` (the "FrozenRouter" trick), which also freezes the
 * next-intl and TanStack Query contexts living above it. Two further problems
 * make it a bad trade even if that were acceptable: the router restores scroll
 * on commit, so the outgoing page jumps to the top before it fades — reading as
 * a glitch rather than a departure — and `AnimatePresence mode="wait"` would
 * add the exit duration to every navigation. Navigation therefore reads as
 * arrival, never departure. React 19.2 ships no `ViewTransition` (only
 * `startTransition`/`useTransition`), and Next's `experimental.viewTransition`
 * needs React's experimental channel, so the framework route is closed too.
 *
 * Note the wrapper carries a transform only while animating; Motion clears it
 * to `none` at rest, so it does not become a containing block for any
 * `position: fixed` descendant. Overlays (sheets, dialogs, toasts) portal to
 * `body` and sit outside this subtree regardless.
 */
export function PageTransition({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const motionPreset = useMotionPreset();

  return (
    <motion.div
      key={pathname}
      data-slot="page-transition"
      variants={pageVariants}
      initial={motionPreset.initial("initial")}
      animate="animate"
      transition={motionPreset.transition(pageTransition)}
    >
      {children}
    </motion.div>
  );
}
