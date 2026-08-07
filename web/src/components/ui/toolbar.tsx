import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Toolbar — a pure layout container for grouping a set of buttons and controls
 * above a list/table (search, filters, view toggles, "New …" actions).
 *
 * Layout only: it owns the horizontal arrangement (wrap, gap, alignment) and
 * nothing else — no focus management, no roving tabindex. For the actual filter
 * / sort / column controls that live *inside* a toolbar, see the sibling
 * `table-toolbar.tsx`.
 *
 * Pure presentational like the `table.tsx` primitives: no `"use client"`, each
 * part carries a kebab-case `data-slot`, extends the native element's props, and
 * spreads `{...props}` last so callers can always override.
 *
 * Shape:
 *   <Toolbar>
 *     <ToolbarGroup>{filter}{search}</ToolbarGroup>   // left controls
 *     <ToolbarGroup>{actions}</ToolbarGroup>          // right actions
 *   </Toolbar>
 *
 * With a single group the `justify-between` root still left-aligns it; use
 * `<ToolbarGroup align="end">` to push a lone group to the right.
 */

export type ToolbarProps = React.ComponentProps<"div">;

function Toolbar({ className, ...props }: ToolbarProps) {
  return (
    <div
      data-slot="toolbar"
      className={cn(
        "flex flex-wrap items-center justify-between gap-2",
        className,
      )}
      {...props}
    />
  );
}

export type ToolbarGroupProps = React.ComponentProps<"div"> & {
  /** `end` pushes the group to the right via `ml-auto` (lone right-aligned group). */
  align?: "start" | "end";
};

function ToolbarGroup({
  className,
  align = "start",
  ...props
}: ToolbarGroupProps) {
  return (
    <div
      data-slot="toolbar-group"
      className={cn(
        "flex flex-wrap items-center gap-2",
        align === "end" && "ml-auto",
        className,
      )}
      {...props}
    />
  );
}

export { Toolbar, ToolbarGroup };
