"use client";

import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type CompactTablePagerProps = {
  page: number;
  maxPage: number;
  pageSize: number;
  pageItemCount: number;
  total: number;
  onPageChange: (next: number) => void;
  rangeLabel: (args: { from: number; to: number; total: number }) => string;
  prevLabel: string;
  nextLabel: string;
  loading?: boolean;
  className?: string;
};

function CompactTablePager({
  page,
  maxPage,
  pageSize,
  pageItemCount,
  total,
  onPageChange,
  rangeLabel,
  prevLabel,
  nextLabel,
  loading = false,
  className,
}: CompactTablePagerProps) {
  const from = pageItemCount === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = pageItemCount === 0 ? 0 : (page - 1) * pageSize + pageItemCount;

  return (
    <div
      className={cn("flex min-h-8 items-center justify-end gap-2", className)}
      aria-busy={loading}
    >
      <span
        className="mr-1 text-xs tabular-nums text-ink-500"
        aria-live="polite"
      >
        {rangeLabel({ from, to, total })}
      </span>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label={prevLabel}
        title={prevLabel}
        disabled={loading || page <= 1}
        onClick={() => onPageChange(Math.max(1, page - 1))}
      >
        <ChevronLeftIcon aria-hidden />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label={nextLabel}
        title={nextLabel}
        disabled={loading || page >= maxPage}
        onClick={() => onPageChange(Math.min(maxPage, page + 1))}
      >
        <ChevronRightIcon aria-hidden />
      </Button>
    </div>
  );
}

export { CompactTablePager, type CompactTablePagerProps };
