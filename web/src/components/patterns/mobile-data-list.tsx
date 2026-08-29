"use client";

import type * as React from "react";

import { MotionList, MotionListItem } from "@/components/patterns/motion-list";
import { StatusFade } from "@/components/patterns/status-fade";
import { Skeleton } from "@/components/ui/skeleton";
import { useInfiniteScroll } from "@/hooks/use-infinite-scroll";
import { cn } from "@/lib/utils";

/**
 * Mobile list shell — the narrow-viewport counterpart to the desktop `Table`.
 * A single white `bg-surface` card clipped to rounded corners; cards flow with
 * the page instead of a fixed scroll viewport, and load more on scroll rather
 * than paginating (the desktop table keeps its frame + pager).
 *
 * Generic over the item type; the caller supplies `renderCard` (typically a
 * {@link DataCard}) and the loading / empty / error state nodes so copy stays
 * in sync with the table view. Pass `infinite` to fetch the next page when the
 * bottom sentinel scrolls into view.
 */
export type MobileDataListProps<T> = {
  items: readonly T[];
  getKey: (item: T) => string;
  renderCard: (item: T) => React.ReactNode;
  isLoading?: boolean;
  isError?: boolean;
  /** Shown when not loading / not errored and `items` is empty. */
  empty?: React.ReactNode;
  /** Shown when `isError`. */
  error?: React.ReactNode;
  /** Skeleton card count while loading. */
  loadingRows?: number;
  /** Bottom-of-list scroll loading. Omit for a non-paginated list. */
  infinite?: {
    hasMore: boolean;
    isFetchingMore: boolean;
    onLoadMore: () => void;
  };
};

const DIVIDER = "shadow-[inset_0_-1px_0_rgb(15_23_42_/_0.04)]";

function SkeletonRow({ divider }: { divider: boolean }) {
  return (
    <div
      aria-busy="true"
      className={cn("flex items-center gap-3 px-4 py-3", divider && DIVIDER)}
    >
      <Skeleton className="size-8 shrink-0 rounded-full" />
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-3 w-1/2" />
      </div>
    </div>
  );
}

export function MobileDataList<T>({
  items,
  getKey,
  renderCard,
  isLoading = false,
  isError = false,
  empty,
  error,
  loadingRows = 5,
  infinite,
}: MobileDataListProps<T>) {
  const showEmpty = !isLoading && !isError && items.length === 0;
  const showItems = !isLoading && !isError && items.length > 0;

  const sentinelRef = useInfiniteScroll({
    hasMore: infinite?.hasMore ?? false,
    isFetchingMore: infinite?.isFetchingMore ?? false,
    onLoadMore: infinite?.onLoadMore ?? (() => {}),
  });

  return (
    <div className="overflow-hidden rounded-3xl bg-surface shadow-elevated">
      {isLoading
        ? Array.from({ length: loadingRows }, (_, i) => i).map((i) => (
            <SkeletonRow key={i} divider={i < loadingRows - 1} />
          ))
        : null}

      {isError ? <StatusFade className="px-4 py-12">{error}</StatusFade> : null}

      {showEmpty ? (
        <StatusFade className="px-4 py-14">{empty}</StatusFade>
      ) : null}

      {showItems ? (
        <MotionList>
          {items.map((item, i) => (
            <MotionListItem
              key={getKey(item)}
              className={i < items.length - 1 ? DIVIDER : undefined}
            >
              {renderCard(item)}
            </MotionListItem>
          ))}
        </MotionList>
      ) : null}

      {/* Infinite-scroll sentinel + "loading more" indicator, only once a first
       * page of items is on screen. */}
      {showItems && infinite ? (
        <>
          {infinite.isFetchingMore ? <SkeletonRow divider={false} /> : null}
          {infinite.hasMore ? (
            <div ref={sentinelRef} aria-hidden className="h-px" />
          ) : null}
        </>
      ) : null}
    </div>
  );
}
