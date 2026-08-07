"use client";

import { Switch as SwitchPrimitive } from "radix-ui";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Borderless project flavour of shadcn's Switch.
 *
 * Diffs vs upstream `pnpm dlx shadcn add switch`:
 *  - Track drops the `border` + `shadow-xs` (project is borderless).
 *  - Track colours map to project palette (brand / ink-400 alpha) instead
 *    of shadcn's primary / input semantics.
 *  - Thumb gets `shadow-action` so the brand drop bleeds through when the
 *    track is on — matches the rest of the console's CTAs.
 *  - All sizes use named Tailwind utilities so the project's
 *    no-arbitrary-tw lint rule stays clean (upstream used arbitrary
 *    `rem` / `calc()` values for height + thumb offset).
 */
function Switch({
  className,
  size = "default",
  ...props
}: React.ComponentProps<typeof SwitchPrimitive.Root> & {
  size?: "sm" | "default";
}) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      data-size={size}
      className={cn(
        "peer group/switch relative inline-flex shrink-0 items-center rounded-full transition-colors outline-none",
        "focus-visible:ring-2 focus-visible:ring-brand/40",
        "disabled:cursor-not-allowed disabled:opacity-60",
        "data-[size=default]:h-5 data-[size=default]:w-9",
        "data-[size=sm]:h-3.5 data-[size=sm]:w-6",
        "data-[state=checked]:bg-brand data-[state=unchecked]:bg-ink-400/50",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className={cn(
          "pointer-events-none block rounded-full bg-surface shadow-action ring-0 transition-transform",
          "group-data-[size=default]/switch:size-4 group-data-[size=sm]/switch:size-3",
          "data-[state=unchecked]:translate-x-0.5",
          "group-data-[size=default]/switch:data-[state=checked]:translate-x-4",
          "group-data-[size=sm]/switch:data-[state=checked]:translate-x-2.5",
        )}
      />
    </SwitchPrimitive.Root>
  );
}

export { Switch };
