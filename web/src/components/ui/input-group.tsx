import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Input Group — wraps a text input together with leading/trailing addons
 * (icons, a dropdown trigger, …) inside ONE field shell. The shell tokens
 * mirror {@link Input}/{@link SelectTrigger} so a grouped field lines up
 * pixel-for-pixel with bare inputs: the container owns the fill + focus ring
 * (driven by `focus-within`) while the inner input stays transparent.
 */
function InputGroup({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="input-group"
      className={cn(
        "flex w-full items-center gap-1 rounded-md bg-ink-wash px-1.5 transition-colors",
        "hover:bg-stripe focus-within:bg-surface focus-within:ring-2 focus-within:ring-brand/30",
        "has-[input:disabled]:pointer-events-none has-[input:disabled]:opacity-60",
        "has-[[aria-invalid=true]]:ring-2 has-[[aria-invalid=true]]:ring-danger-soft",
        className,
      )}
      {...props}
    />
  );
}

/**
 * Bare input for use inside {@link InputGroup}. Drops the standalone Input's
 * own fill/ring (the group provides them) but keeps the same padding rhythm and
 * `mono` affordance. Container `px-1.5` + input `px-1.5` sum to the `px-3` of a
 * plain Input.
 */
function InputGroupInput({
  className,
  type,
  mono = false,
  ...props
}: React.ComponentProps<"input"> & { mono?: boolean }) {
  return (
    <input
      type={type}
      data-slot="input-group-input"
      className={cn(
        "w-full min-w-0 bg-transparent px-1.5 py-2.5 text-md text-ink-900 outline-none",
        "placeholder:text-ink-400 selection:bg-brand-soft selection:text-brand",
        "disabled:cursor-not-allowed",
        mono && "font-mono placeholder:font-sans",
        className,
      )}
      {...props}
    />
  );
}

/**
 * Leading / trailing slot inside an {@link InputGroup}. `align="end"` (default)
 * pins it after the input; `align="start"` before it.
 */
function InputGroupAddon({
  className,
  align = "end",
  ...props
}: React.ComponentProps<"div"> & { align?: "start" | "end" }) {
  return (
    <div
      data-slot="input-group-addon"
      className={cn(
        "flex shrink-0 items-center text-ink-400",
        align === "start" ? "order-first" : "order-last",
        className,
      )}
      {...props}
    />
  );
}

export { InputGroup, InputGroupInput, InputGroupAddon };
