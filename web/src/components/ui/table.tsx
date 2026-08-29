import type * as React from "react";

import {
  STAGGER_MAX,
  TABLE_ROW_ENTER_MS,
  TABLE_ROW_STAGGER_MS,
} from "@/lib/motion";
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
  /** Content rendered in the frame above the table viewport. */
  header?: React.ReactNode;
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
  /** Let content determine height instead of reserving the 10-row viewport. */
  compact?: boolean;
  /** Remove the gray frame, its padding, and elevation. */
  frameless?: boolean;
  /** Opt into inline expanded-row spotlight styling. */
  rowSpotlight?: boolean;
};

function Table({
  className,
  containerClassName,
  header,
  scrollClassName,
  footer,
  dividers = false,
  compact = false,
  frameless = false,
  rowSpotlight = false,
  ...props
}: TableProps) {
  return (
    // Outer shell owns the shadow and the visible rounded outline so that
    // clip-path on the inner container does not swallow the box-shadow.
    <div
      className={cn(
        compact ? "rounded-xl" : "rounded-3xl",
        "shadow-elevated",
        frameless && "rounded-none shadow-none",
        containerClassName,
      )}
    >
      {/* clip-path is the only reliable way to clip sticky compositor layers.
       * overflow:hidden stops working for position:sticky once the browser
       * promotes the element to its own GPU layer on scroll. clip-path is
       * applied post-compositing and therefore clips all sub-layers. */}
      <div
        data-slot="table-container"
        data-compact={compact ? "true" : undefined}
        className={cn(
          "relative overflow-hidden bg-table-frame px-1 pb-1",
          compact ? "rounded-xl" : "rounded-3xl",
          frameless && "rounded-none bg-transparent p-0",
        )}
      >
        {header}
        <div
          data-slot="table-scroll"
          data-compact={compact ? "true" : undefined}
          className={cn(
            compact
              ? "overflow-x-auto rounded-b-xl"
              : "h-table-viewport overflow-x-hidden overflow-y-auto rounded-b-table-pill bg-surface",
            frameless && "rounded-none",
            scrollClassName,
          )}
        >
          <table
            data-slot="table"
            data-dividers={dividers ? undefined : "off"}
            data-compact={compact ? "true" : undefined}
            data-row-spotlight={rowSpotlight ? "true" : undefined}
            className={cn(
              "ui-table w-full border-separate border-spacing-0",
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
        <div
          data-slot="table-arc-left"
          className={compact ? "hidden" : undefined}
          aria-hidden
        />
        <div
          data-slot="table-arc-right"
          className={compact ? "hidden" : undefined}
          aria-hidden
        />
      </div>
    </div>
  );
}

export type TableHeaderProps = React.ComponentProps<"thead">;

function TableHeader({ className, ...props }: TableHeaderProps) {
  return <thead data-slot="table-header" className={className} {...props} />;
}

export type TableBodyProps = React.ComponentProps<"tbody"> & {
  /** Keep stale rows visible but inert while a replacement dataset loads. */
  refreshing?: boolean;
};

function TableBody({
  className,
  refreshing = false,
  ...props
}: TableBodyProps) {
  return (
    <tbody
      data-slot="table-body"
      data-refreshing={refreshing ? "true" : undefined}
      aria-busy={refreshing || undefined}
      inert={refreshing ? true : undefined}
      className={cn("table-body-motion", className)}
      {...props}
    />
  );
}

export type TableFooterProps = React.ComponentProps<"tfoot">;

function TableFooter({ className, ...props }: TableFooterProps) {
  return <tfoot data-slot="table-footer" className={className} {...props} />;
}

export type TableRowProps = React.ComponentProps<"tr"> & {
  /** Join this row to a following TableExpandedRow as the active detail. */
  expanded?: boolean;
  /**
   * Side-Sheet selected state. The detail lives in a separate Sheet, so this is
   * a light row highlight only.
   */
  active?: boolean;
  /**
   * Position in the list, which staggers the row's fade-in. Pass the `map`
   * index; omit it for rows that should appear immediately (filler rows, state
   * rows, rows inside a nested table).
   *
   * Driven by `data-enter` + a `--row-i` custom property rather than
   * `motion.tr`, for two reasons. This component stays pure-presentational (no
   * `"use client"`, matching the `data-dividers` precedent above), and the
   * animation stays opacity-only. See DESIGN.md §7.
   */
  enterIndex?: number;
};

function TableRow({
  className,
  expanded,
  active,
  enterIndex,
  style,
  ...props
}: TableRowProps) {
  // `group` enables `group-hover:` on the cells (hover wash is painted per-cell
  // so the rounded corner-cell clip still wins, per the original Firefox note).
  return (
    <tr
      data-slot="table-row"
      data-state={
        expanded === undefined ? undefined : expanded ? "open" : "closed"
      }
      data-active={active ? "true" : undefined}
      data-enter={enterIndex === undefined ? undefined : ""}
      className={cn("group transition-colors", className)}
      style={
        enterIndex === undefined
          ? style
          : // Clamped so a long or infinite list doesn't push the last rows
            // seconds out; past the cap everything shares the final delay.
            ({
              ...style,
              "--row-i": Math.min(enterIndex, STAGGER_MAX),
              "--row-enter-duration": `${TABLE_ROW_ENTER_MS}ms`,
              "--row-stagger-step": `${TABLE_ROW_STAGGER_MS}ms`,
            } as React.CSSProperties)
      }
      {...props}
    />
  );
}

export type TableExpandedRowProps = React.ComponentProps<"tr"> & {
  colSpan: number;
  cellClassName?: string;
};

function TableExpandedRow({
  colSpan,
  cellClassName,
  children,
  ...props
}: TableExpandedRowProps) {
  return (
    <tr data-slot="table-expanded-row" {...props}>
      <td
        colSpan={colSpan}
        className={cn("h-auto bg-surface p-0", cellClassName)}
      >
        <div data-slot="table-expanded-content" className="min-w-0 w-full">
          {children}
        </div>
      </td>
    </tr>
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
  /** Draw the 1px row hairline at the cell's bottom. */
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
  TableExpandedRow,
  TableHead,
  TableCell,
  TableCaption,
};
