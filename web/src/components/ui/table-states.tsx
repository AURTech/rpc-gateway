"use client";

import type { ReactNode } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Link } from "@/i18n/navigation";
import { cn } from "@/lib/utils";

export const TABLE_VIEWPORT_ROWS = 10;

/** Placeholder skeleton rows while a table page loads. Renders one skeleton per
 *  column so the bars line up under the real (non-skeleton) header, and the last
 *  column mirrors the right-aligned actions/column-toggle cell. */
export type TableLoadingRowsProps = {
  colSpan: number;
  rows?: number;
};

// Repeating width palette (standard Tailwind scale — no arbitrary values) so the
// per-column bars vary slightly instead of reading as one uniform block.
const LOADING_CELL_WIDTHS = ["w-28", "w-20", "w-24", "w-16", "w-24"];

// Header labels are shorter than body content — narrower bars read as column
// titles rather than data.
const LOADING_HEAD_WIDTHS = ["w-16", "w-12", "w-16", "w-14", "w-16"];

/** Skeleton `<thead>` matching the real header's column count, so the header row
 *  animates in step with the body instead of sitting as solid text above
 *  shimmering rows. Drop in place of the real `<TableHeader>` while loading. */
export type TableLoadingHeaderProps = {
  colSpan: number;
};

function TableLoadingHeader({ colSpan }: TableLoadingHeaderProps) {
  return (
    <TableHeader aria-busy="true">
      <TableRow>
        {Array.from({ length: colSpan }, (_, c) => c).map((c) => {
          const isActions = c === colSpan - 1;
          return (
            <TableHead key={c}>
              <Skeleton
                className={
                  isActions
                    ? "ml-auto h-5 w-16"
                    : `h-4 ${LOADING_HEAD_WIDTHS[c % LOADING_HEAD_WIDTHS.length]}`
                }
              />
            </TableHead>
          );
        })}
      </TableRow>
    </TableHeader>
  );
}

function TableLoadingRows({
  colSpan,
  rows = TABLE_VIEWPORT_ROWS,
}: TableLoadingRowsProps) {
  return (
    <>
      {Array.from({ length: rows }, (_, i) => i).map((i) => (
        <tr key={i} aria-busy="true">
          {Array.from({ length: colSpan }, (_, c) => c).map((c) => {
            const isActions = c === colSpan - 1;
            return (
              <td key={c} className="h-table-row bg-surface px-4">
                <Skeleton
                  className={
                    isActions
                      ? "ml-auto h-5 w-5"
                      : `h-5 ${LOADING_CELL_WIDTHS[c % LOADING_CELL_WIDTHS.length]}`
                  }
                />
              </td>
            );
          })}
        </tr>
      ))}
    </>
  );
}

export type TableErrorRowProps = {
  colSpan: number;
  title: string;
  body: string;
  retry: string;
  onRetry: () => void;
};

function TableErrorRow({
  colSpan,
  title,
  body,
  retry,
  onRetry,
}: TableErrorRowProps) {
  return (
    // `data-enter` fades the row in via the `.ui-table` rule in globals.css —
    // the same opacity-only entrance the data rows use. No index, so it lands
    // without a stagger delay.
    <tr className="h-full" data-enter="" data-table-state="error">
      <td className="h-full bg-surface px-4" colSpan={colSpan}>
        <div
          role="alert"
          className="mx-auto flex h-full max-w-prose-narrow flex-col items-center justify-center gap-2 text-center"
        >
          <p className="text-lg font-semibold text-ink-900">{title}</p>
          <p className="text-md text-ink-500">{body}</p>
          <button
            type="button"
            onClick={onRetry}
            className="mt-2 inline-flex h-9 items-center rounded-md bg-brand-soft px-4 text-sm font-semibold text-brand transition-colors hover:bg-brand hover:text-white"
          >
            {retry}
          </button>
        </div>
      </td>
    </tr>
  );
}

export type TableEmptyCopy = {
  title: string;
  body: string;
  cta: string;
  href?: string;
  action?: ReactNode;
};

export type TableEmptyRowProps = {
  colSpan: number;
  hasFilter: boolean;
  empty: TableEmptyCopy;
  filtered: TableEmptyCopy;
  onClear: () => void;
  cellClassName?: string;
};

function TableEmptyRow({
  colSpan,
  hasFilter,
  empty,
  filtered,
  onClear,
  cellClassName,
}: TableEmptyRowProps) {
  const copy = hasFilter ? filtered : empty;
  return (
    // See TableErrorRow: `data-enter` reuses the opacity-only row entrance.
    <tr className="h-full" data-enter="" data-table-state="empty">
      <td
        className={cn("h-full bg-surface px-4", cellClassName)}
        colSpan={colSpan}
      >
        <div className="mx-auto flex h-full max-w-prose-narrow flex-col items-center justify-center gap-2 text-center">
          <p className="text-lg font-semibold text-ink-900">{copy.title}</p>
          <p className="text-md text-ink-500">{copy.body}</p>
          {hasFilter ? (
            <button
              type="button"
              onClick={onClear}
              className="mt-2 inline-flex h-9 items-center rounded-md bg-ink-wash px-4 text-sm font-semibold text-ink-700 transition-colors hover:bg-stripe"
            >
              {copy.cta}
            </button>
          ) : copy.action ? (
            <div className="mt-2">{copy.action}</div>
          ) : copy.href ? (
            <Link
              href={copy.href}
              className="mt-2 inline-flex h-9 items-center rounded-md bg-brand-soft px-4 text-sm font-semibold text-brand transition-colors hover:bg-brand hover:text-white"
            >
              {copy.cta}
            </Link>
          ) : null}
        </div>
      </td>
    </tr>
  );
}

export type TableFillerRowsProps = { count: number; colSpan: number };

function TableFillerRows({ count, colSpan }: TableFillerRowsProps) {
  if (count <= 0) return null;
  return (
    <>
      {Array.from({ length: count }, (_, i) => i).map((i) => (
        <tr key={i}>
          <td className="h-table-row bg-surface" colSpan={colSpan} />
        </tr>
      ))}
    </>
  );
}

export {
  TableLoadingHeader,
  TableLoadingRows,
  TableErrorRow,
  TableEmptyRow,
  TableFillerRows,
};
