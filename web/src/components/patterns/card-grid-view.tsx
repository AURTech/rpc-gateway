"use client";

import { Fragment, type ReactNode } from "react";

import { MotionList, MotionListItem } from "@/components/patterns/motion-list";
import { StatusFade } from "@/components/patterns/status-fade";
import { Skeleton } from "@/components/ui/skeleton";
import type { TableEmptyCopy } from "@/components/ui/table-states";
import { useInfiniteScroll } from "@/hooks/use-infinite-scroll";
import { cn } from "@/lib/utils";

/**
 * Card-grid list shell — the card-first counterpart to {@link ResponsiveListView}.
 * Renders items as a responsive grid of cards on every viewport (no desktop
 * table), and loads more on scroll rather than paginating.
 *
 * Owns the cross-cutting glue so pages don't re-wire it: the responsive grid,
 * loading skeletons, the shared empty / filtered-empty / error nodes (same copy
 * shape and styling as `ResponsiveListView`), and the infinite-scroll sentinel.
 * The page supplies only `renderCard`, the data/async flags, the `infinite`
 * config, and the `states` copy. Per-card local state (dialogs, mutations) stays
 * inside the card component. Takes strings / nodes only — no `next-intl`.
 */
export type CardGridViewProps<T> = {
  items: readonly T[];
  getKey: (item: T) => string;
  renderCard: (item: T) => ReactNode;
  isLoading?: boolean;
  isError?: boolean;
  /** Skeleton card count while loading. */
  loadingCards?: number;
  /** Custom skeleton matching the page's card shape; defaults to a compact row. */
  renderSkeleton?: () => ReactNode;
  /** Extra classes for the grid container (e.g. to tune column count). */
  gridClassName?: string;

  infinite?: {
    hasMore: boolean;
    isFetchingMore: boolean;
    onLoadMore: () => void;
  };

  states: {
    hasActiveFilter: boolean;
    onClearFilter: () => void;
    onRetry: () => void;
    empty: TableEmptyCopy;
    /** Defaults to `empty` (pages with no filters). */
    filtered?: TableEmptyCopy;
    error: { title: string; body: string; retry: string };
  };
};

const GRID = "grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3";

function CardSkeleton() {
  return (
    <div
      aria-busy="true"
      className="flex items-center gap-3 rounded-xl bg-surface px-4 py-3 shadow-card"
    >
      <Skeleton className="size-8 shrink-0 rounded-lg" />
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-3 w-2/3" />
      </div>
      <Skeleton className="h-5 w-16 shrink-0 rounded-full" />
    </div>
  );
}

export function CardGridView<T>({
  items,
  getKey,
  renderCard,
  isLoading = false,
  isError = false,
  loadingCards = 6,
  renderSkeleton,
  gridClassName,
  infinite,
  states,
}: CardGridViewProps<T>) {
  const filtered = states.filtered ?? states.empty;
  const showItems = !isLoading && !isError && items.length > 0;
  const showEmpty = !isLoading && !isError && items.length === 0;
  const skeleton = renderSkeleton ?? (() => <CardSkeleton />);

  const sentinelRef = useInfiniteScroll({
    hasMore: infinite?.hasMore ?? false,
    isFetchingMore: infinite?.isFetchingMore ?? false,
    onLoadMore: infinite?.onLoadMore ?? (() => {}),
  });

  if (isLoading) {
    return (
      <div className={cn(GRID, gridClassName)}>
        {Array.from({ length: loadingCards }, (_, i) => i).map((i) => (
          <Fragment key={i}>{skeleton()}</Fragment>
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <StatusFade
        role="alert"
        className="mx-auto flex max-w-prose-narrow flex-col items-center gap-2 py-14 text-center"
      >
        <p className="text-lg font-semibold text-ink-900">
          {states.error.title}
        </p>
        <p className="text-md text-ink-500">{states.error.body}</p>
        <button
          type="button"
          onClick={states.onRetry}
          className="mt-2 inline-flex h-9 items-center rounded-md bg-brand-soft px-4 text-sm font-semibold text-brand transition-colors hover:bg-brand hover:text-white"
        >
          {states.error.retry}
        </button>
      </StatusFade>
    );
  }

  if (showEmpty) {
    return (
      <StatusFade className="mx-auto flex max-w-prose-narrow flex-col items-center gap-2 py-14 text-center">
        <p className="text-lg font-semibold text-ink-900">
          {states.hasActiveFilter ? filtered.title : states.empty.title}
        </p>
        <p className="text-md text-ink-500">
          {states.hasActiveFilter ? filtered.body : states.empty.body}
        </p>
        {states.hasActiveFilter ? (
          <button
            type="button"
            onClick={states.onClearFilter}
            className="mt-2 inline-flex h-9 items-center rounded-md bg-ink-wash px-4 text-sm font-semibold text-ink-700 transition-colors hover:bg-stripe"
          >
            {filtered.cta}
          </button>
        ) : null}
      </StatusFade>
    );
  }

  return (
    <>
      {/* MotionList absorbs the grid element rather than nesting inside it —
          an extra level would collapse every card into a single grid cell. */}
      <MotionList className={cn(GRID, gridClassName)}>
        {showItems
          ? items.map((item) => (
              <MotionListItem key={getKey(item)}>
                {renderCard(item)}
              </MotionListItem>
            ))
          : null}
        {/* Fetching-more skeleton fills the next grid cell. */}
        {infinite?.isFetchingMore ? skeleton() : null}
      </MotionList>

      {/* Infinite-scroll sentinel, only once a first page is on screen. */}
      {showItems && infinite?.hasMore ? (
        <div ref={sentinelRef} aria-hidden className="h-px" />
      ) : null}
    </>
  );
}
