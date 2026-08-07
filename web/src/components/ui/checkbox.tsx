"use client";

import { CheckIcon } from "lucide-react";
import { Checkbox as CheckboxPrimitive } from "radix-ui";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Borderless-friendly project flavour of shadcn's Checkbox.
 *
 * Diffs vs upstream `pnpm dlx shadcn add checkbox`:
 *  - Drops dark-mode classes (project ships light-only).
 *  - Replaces upstream's arbitrary 4px corner radius with the named
 *    `rounded-sm` token so the no-arbitrary-tw lint stays clean.
 *  - Border + bg map to project palette (ink-400 alpha → brand on check)
 *    instead of shadcn's `border-input` / `border-primary`.
 */
function Checkbox({
  className,
  ...props
}: React.ComponentProps<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        "peer size-4 shrink-0 rounded-sm border border-ink-400/40 bg-surface transition-colors outline-none",
        "focus-visible:ring-2 focus-visible:ring-brand/40",
        "disabled:cursor-not-allowed disabled:opacity-60",
        "data-[state=checked]:border-brand data-[state=checked]:bg-brand data-[state=checked]:text-white",
        "aria-invalid:border-danger aria-invalid:ring-2 aria-invalid:ring-danger/30",
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="grid place-content-center text-current"
      >
        <CheckIcon className="size-3.5" />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}

export { Checkbox };
