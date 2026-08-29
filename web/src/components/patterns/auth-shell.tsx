"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";

import { useMotionPreset } from "@/hooks/use-motion-preset";
import { easeEmphasized } from "@/lib/motion";
import { cn } from "@/lib/utils";

/**
 * Centered shell shared by the sign-in and OAuth-callback screens: a soft-gray
 * canvas, the screen's card, and an optional footnote. Keeps the whole auth
 * flow on one visual language. The column fades up once on mount (a single
 * element, no choreography) and respects reduced-motion.
 */
export function AuthShell({
  children,
  footnote,
  className,
}: {
  children: ReactNode;
  footnote?: ReactNode;
  className?: string;
}) {
  const motionPreset = useMotionPreset();

  return (
    <main className="flex min-h-svh items-center justify-center bg-page-bg px-6 py-12">
      <motion.div
        className={cn(
          "flex w-full max-w-sm flex-col items-center gap-8",
          className,
        )}
        initial={motionPreset.initial({ opacity: 0, y: 8 })}
        animate={{ opacity: 1, y: 0 }}
        transition={motionPreset.transition({
          duration: 0.2,
          ease: easeEmphasized,
        })}
      >
        {children}

        {footnote ? (
          <p className="text-center text-sm text-ink-400">{footnote}</p>
        ) : null}
      </motion.div>
    </main>
  );
}
