import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Text input. The base style is the de-facto field style used across the
 * dashboard dialogs (soft fill, lifts to surface on focus). Pass `mono` for
 * monospaced value entry (e.g. RPC method names) while keeping the placeholder
 * in the sans font.
 */
function Input({
  className,
  type,
  mono = false,
  ...props
}: React.ComponentProps<"input"> & { mono?: boolean }) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        // No background transition: the focus fill (ink-wash → surface) is
        // applied instantly. Animating it left a faint hairline fading under
        // the box on focus/blur; an instant swap removes that artifact.
        "w-full min-w-0 rounded-md bg-ink-wash px-3 py-3 text-md text-ink-900 outline-none",
        "placeholder:text-ink-400 selection:bg-brand-soft selection:text-brand",
        "hover:bg-stripe focus:bg-surface focus-visible:ring-2 focus-visible:ring-brand/30",
        "disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-60",
        "aria-invalid:ring-2 aria-invalid:ring-danger-soft",
        mono && "font-mono placeholder:font-sans",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
