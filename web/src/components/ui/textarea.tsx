import type * as React from "react";

import { cn } from "@/lib/utils";

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "min-h-20 w-full resize-y rounded-md bg-ink-wash px-3 py-2.5 text-md text-ink-900 transition-colors outline-none",
        "placeholder:text-ink-400 selection:bg-brand-soft selection:text-brand",
        "hover:bg-stripe focus:bg-surface focus-visible:ring-2 focus-visible:ring-brand/30",
        "disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-60",
        "aria-invalid:ring-2 aria-invalid:ring-danger-soft",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
