"use client";

import { cva, type VariantProps } from "class-variance-authority";
import { Label as LabelPrimitive } from "radix-ui";
import type * as React from "react";

import { cn } from "@/lib/utils";

const labelVariants = cva("select-none", {
  variants: {
    variant: {
      default:
        "flex items-center gap-2 text-sm leading-none font-medium group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-50 peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
      // Field label sitting above a form control (matches the dashboard forms).
      field: "block text-sm font-semibold text-ink-900",
    },
  },
  defaultVariants: {
    variant: "default",
  },
});

function Label({
  className,
  variant = "default",
  ...props
}: React.ComponentProps<typeof LabelPrimitive.Root> &
  VariantProps<typeof labelVariants>) {
  return (
    <LabelPrimitive.Root
      data-slot="label"
      data-variant={variant}
      className={cn(labelVariants({ variant }), className)}
      {...props}
    />
  );
}

export { Label, labelVariants };
