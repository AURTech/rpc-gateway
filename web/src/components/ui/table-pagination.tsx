"use client";

import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import { Skeleton } from "@/components/ui/skeleton";
import { buildPaginationRange } from "@/lib/pagination-range";

export type TablePaginationProps = {
  page: number;
  maxPage: number;
  pageSize: number;
  /** Items on the active page (drives the "to" end of the range summary). */
  pageItemCount: number;
  total: number;
  onPageChange: (next: number) => void;
  rangeLabel: (args: { from: number; to: number; total: number }) => string;
  prevLabel: string;
  nextLabel: string;
};

/**
 * Table footer content: a range summary on the left and HeroUI-style
 * pagination pushed to the right. Renders inside a `<TableFooter>` cell.
 */
function TablePagination({
  page,
  maxPage,
  pageSize,
  pageItemCount,
  total,
  onPageChange,
  rangeLabel,
  prevLabel,
  nextLabel,
}: TablePaginationProps) {
  const range = buildPaginationRange(page, maxPage);
  const from = pageItemCount === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = (page - 1) * pageSize + pageItemCount;
  return (
    <div className="flex w-full flex-col items-center justify-between gap-3 sm:flex-row">
      <span className="text-sm tabular-nums text-ink-500">
        {rangeLabel({ from, to, total })}
      </span>
      <Pagination className="mx-0 w-auto justify-end">
        <PaginationContent>
          <PaginationItem>
            <PaginationPrevious
              href="#"
              aria-label={prevLabel}
              disabled={page <= 1}
              onClick={() => onPageChange(Math.max(1, page - 1))}
            >
              {prevLabel}
            </PaginationPrevious>
          </PaginationItem>
          {range.map((entry) => {
            if (entry === "ellipsis-left" || entry === "ellipsis-right") {
              // At most one of each ellipsis side is emitted, so the literal
              // slug is a stable, unique key.
              return (
                <PaginationItem key={entry}>
                  <PaginationEllipsis />
                </PaginationItem>
              );
            }
            return (
              <PaginationItem key={entry}>
                <PaginationLink
                  href="#"
                  isActive={entry === page}
                  onClick={() => onPageChange(entry)}
                >
                  {entry}
                </PaginationLink>
              </PaginationItem>
            );
          })}
          <PaginationItem>
            <PaginationNext
              href="#"
              aria-label={nextLabel}
              disabled={page >= maxPage}
              onClick={() => onPageChange(Math.min(maxPage, page + 1))}
            >
              {nextLabel}
            </PaginationNext>
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    </div>
  );
}

/**
 * Loading placeholder for {@link TablePagination}. Mirrors its layout (range
 * summary left, pager buttons right) so the footer keeps its height while a page
 * loads instead of collapsing and snapping in. Drop into the same `px-4 py-3`
 * wrapper the real footer uses.
 */
function TablePaginationSkeleton() {
  return (
    <div
      aria-busy="true"
      className="flex w-full flex-col items-center justify-between gap-3 sm:flex-row"
    >
      <Skeleton className="h-5 w-40" />
      <div className="flex items-center gap-2">
        <Skeleton className="size-9 rounded-md" />
        <Skeleton className="size-9 rounded-md" />
        <Skeleton className="size-9 rounded-md" />
        <Skeleton className="size-9 rounded-md" />
      </div>
    </div>
  );
}

export { TablePagination, TablePaginationSkeleton };
