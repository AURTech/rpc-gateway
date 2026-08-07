"use client";

import { useEffect, useRef } from "react";

/**
 * Bottom-of-list infinite scroll. The consumer renders the returned ref on a
 * sentinel `<div>` at the end of the list; an `IntersectionObserver` watches it
 * and calls `onLoadMore` once it scrolls into view — as long as there is more
 * to load and a fetch isn't already in flight.
 *
 * The observer re-subscribes when `hasMore` / `isFetchingMore` change, so after
 * a page finishes loading it re-arms and (if the sentinel is still visible, e.g.
 * a short page) fetches the next one until the list is exhausted. `onLoadMore`
 * is read through a ref so a changing callback identity doesn't churn the
 * observer. No-ops where `IntersectionObserver` is absent (SSR / jsdom).
 */
export function useInfiniteScroll({
  hasMore,
  isFetchingMore,
  onLoadMore,
}: {
  hasMore: boolean;
  isFetchingMore: boolean;
  onLoadMore: () => void;
}) {
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const onLoadMoreRef = useRef(onLoadMore);
  onLoadMoreRef.current = onLoadMore;

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el || !hasMore || isFetchingMore) return;
    if (typeof IntersectionObserver === "undefined") return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          onLoadMoreRef.current();
        }
      },
      // Prefetch slightly before the sentinel is fully in view.
      { rootMargin: "200px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasMore, isFetchingMore]);

  return sentinelRef;
}
