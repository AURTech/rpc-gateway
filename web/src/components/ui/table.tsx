import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Table primitives — shadcn-aligned (the components.build reference set) with
 * the project's "HeroUI white pill in a gray frame" styling.
 *
 * Pure presentational: no `"use client"`, every part carries a kebab-case
 * `data-slot`, extends the native element's props, and spreads `{...props}`
 * last so callers can always override.
 *
 * Visual model: `Table` paints the outer gray frame + clips it to a rounded
 * card; tbody cells are white, and the corner-cell rounding (the "pill") lives
 * in the `.ui-table` CSS block in globals.css.
 */

export type TableProps = React.ComponentProps<"table"> & {
  containerClassName?: string;
  /** Override the fixed scroll-viewport height (defaults to 10 rows). */
  scrollClassName?: string;
  /** Rendered below the scroll viewport, inside the frame — for pagination so
   *  it never scrolls away with the rows. */
  footer?: React.ReactNode;
  /** Show the 1px hairline between rows. Defaults to false (the active
   *  design hides row dividers). When false, every row's bottom hairline is
   *  suppressed table-wide (overrides per-cell `divider`). Pass `dividers` to
   *  opt back in. Driven by the `data-dividers` attribute + `.ui-table` CSS so
   *  this component can stay pure-presentational (no Context / "use client"). */
  dividers?: boolean;
};

function Table({
  className,
  containerClassName,
  scrollClassName,
  footer,
  dividers = false,
  ...props
}: TableProps) {
  return (
    // Outer shell owns the shadow and the visible rounded outline so that
    // clip-path on the inner container does not swallow the box-shadow.
    <div className={cn("rounded-3xl shadow-elevated", containerClassName)}>
      {/* clip-path is the only reliable way to clip sticky compositor layers.
       * overflow:hidden stops working for position:sticky once the browser
       * promotes the element to its own GPU layer on scroll. clip-path is
       * applied post-compositing and therefore clips all sub-layers. */}
      <div
        data-slot="table-container"
        className="relative overflow-hidden rounded-3xl bg-table-frame px-1 pb-1"
      >
        <div
          data-slot="table-scroll"
          className={cn(
            "h-table-viewport overflow-x-hidden overflow-y-auto rounded-b-table-pill",
            scrollClassName,
          )}
        >
          <table
            data-slot="table"
            data-dividers={dividers ? undefined : "off"}
            className={cn(
              "ui-table w-full min-h-full border-separate border-spacing-0",
              className,
            )}
            {...props}
          />
        </div>
        {footer}
        {/* Rounded top-corner arcs for the white pill, always at the
         * header/body junction. CSS tr:first-child only rounds the first DOM
         * row; after scrolling the first visible row has no radius. These
         * frame-coloured wedges (radial-gradient concave notch, see globals)
         * fill the arc area without covering any cell text — at px-4 (16 px)
         * the arc's solid region is <0.5 px tall, geometrically invisible. */}
        <div data-slot="table-arc-left" aria-hidden />
        <div data-slot="table-arc-right" aria-hidden />
      </div>
    </div>
  );
}

export type TableHeaderProps = React.ComponentProps<"thead">;

function TableHeader({ className, ...props }: TableHeaderProps) {
  return <thead data-slot="table-header" className={className} {...props} />;
}

export type TableBodyProps = React.ComponentProps<"tbody">;

function TableBody({ className, ...props }: TableBodyProps) {
  return <tbody data-slot="table-body" className={className} {...props} />;
}

export type TableFooterProps = React.ComponentProps<"tfoot">;

function TableFooter({ className, ...props }: TableFooterProps) {
  return <tfoot data-slot="table-footer" className={className} {...props} />;
}

export type TableRowProps = React.ComponentProps<"tr"> & {
  /**
   * Inline row-drawer open state. Drives the table's "spotlight" design — the
   * row + its `TableExpandedRow` float as one card while the rest dim to the
   * frame colour (see globals.css). Use only with the inline-drawer pattern.
   */
  expanded?: boolean;
  /**
   * Side-Sheet selected state. The detail lives in a separate Sheet, so this is
   * a light row highlight only — it must NOT dim the rest of the table the way
   * `expanded` does. Mutually exclusive with `expanded`.
   */
  active?: boolean;
};

function TableRow({ className, expanded, active, ...props }: TableRowProps) {
  // `group` enables `group-hover:` on the cells (hover wash is painted per-cell
  // so the rounded corner-cell clip still wins, per the original Firefox note).
  return (
    <tr
      data-slot="table-row"
      data-state={
        expanded === undefined ? undefined : expanded ? "open" : "closed"
      }
      data-active={active ? "true" : undefined}
      className={cn("group transition-colors", className)}
      {...props}
    />
  );
}

export type TableHeadProps = React.ComponentProps<"th"> & {
  align?: "left" | "right";
  srOnly?: boolean;
};

function TableHead({
  className,
  align = "left",
  srOnly,
  ...props
}: TableHeadProps) {
  return (
    <th
      data-slot="table-head"
      scope="col"
      className={cn(
        "h-table-head px-4 text-xs font-medium text-ink-500",
        align === "right" ? "text-right" : "text-left",
        srOnly && "sr-only",
        className,
      )}
      {...props}
    />
  );
}

export type TableCellProps = React.ComponentProps<"td"> & {
  align?: "left" | "right";
  /** Draw the 1px row hairline at the cell's bottom. Off for expanded rows so
   *  the row + drawer read as one continuous shape. */
  divider?: boolean;
};

function TableCell({
  className,
  align = "left",
  divider = true,
  ...props
}: TableCellProps) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        "h-table-row bg-surface px-4 text-sm text-ink-900 transition-colors group-hover:bg-row-hover",
        divider && "shadow-[inset_0_-1px_0_rgb(15_23_42_/_0.04)]",
        align === "right" && "text-right",
        className,
      )}
      {...props}
    />
  );
}

export type TableExpandedRowProps = {
  colSpan: number;
  className?: string;
  children: React.ReactNode;
  /** Ref on the drawer `<tr>` so the row can scroll it into view on expand. */
  rowRef?: React.Ref<HTMLTableRowElement>;
};

function TableExpandedRow({
  colSpan,
  className,
  children,
  rowRef,
}: TableExpandedRowProps) {
  // Must be conditionally MOUNTED by the caller (never display:none) so the
  // `.ui-table tbody tr:last-child` corner CSS keeps targeting the real last row.
  return (
    <tr ref={rowRef} data-slot="table-expanded-row">
      <td colSpan={colSpan} className={cn("bg-surface p-0", className)}>
        {/* Hard 2-row cap: the drawer never grows the fixed viewport, whatever
         * its content. The drawer body is laid out to fit without scrolling. */}
        <div className="max-h-table-drawer overflow-hidden">{children}</div>
      </td>
    </tr>
  );
}

export type TableCaptionProps = React.ComponentProps<"caption">;

function TableCaption({ className, ...props }: TableCaptionProps) {
  return (
    <caption
      data-slot="table-caption"
      className={cn("sr-only", className)}
      {...props}
    />
  );
}

export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableRow,
  TableHead,
  TableCell,
  TableExpandedRow,
  TableCaption,
};
