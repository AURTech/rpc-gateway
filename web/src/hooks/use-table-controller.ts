"use client";

import { useCallback, useState } from "react";

/**
 * Bundles the generic cross-cutting state every list table needs — search
 * query, pagination, sort slug, column visibility, and row expansion.
 *
 * Domain-specific filters (chain/network/status/…) stay in the page; when they
 * change, the page calls `resetPage()` so paging restarts at 1. `setQuery` and
 * `setSort` reset the page automatically.
 *
 * `sort` is a composite `field-order` slug; the page splits it into its API
 * params. Column visibility enforces a minimum of one visible column.
 */
export type TableController<C extends string> = {
  query: string;
  setQuery: (q: string) => void;
  page: number;
  setPage: (p: number) => void;
  sort: string;
  setSort: (next: string) => void;
  visibleColumns: Set<C>;
  setVisibleColumns: (next: Set<C>) => void;
  isColumnVisible: (key: C) => boolean;
  expanded: Set<string>;
  toggleExpanded: (id: string) => void;
  isExpanded: (id: string) => boolean;
  /** Close any open row (no-op when none is open). */
  collapse: () => void;
  resetPage: () => void;
};

export function useTableController<C extends string>(opts: {
  allColumns: readonly C[];
  initialVisibleColumns?: readonly C[];
  initialSort?: string;
}): TableController<C> {
  const { allColumns, initialVisibleColumns, initialSort = "" } = opts;

  const [query, setQueryState] = useState("");
  const [page, setPageState] = useState(1);
  const [sort, setSortState] = useState(initialSort);
  const [visibleColumns, setVisibleColumnsState] = useState<Set<C>>(
    () => new Set(initialVisibleColumns ?? allColumns),
  );
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  // Changing pages collapses the open drawer: the fixed-height viewport only
  // ever shows one drawer, and a stale id from another page renders nothing.
  const setPage = useCallback((p: number) => {
    setPageState(p);
    setExpanded((prev) => (prev.size === 0 ? prev : new Set()));
  }, []);

  const resetPage = useCallback(() => setPage(1), [setPage]);

  const setQuery = useCallback(
    (q: string) => {
      setPage(1);
      setQueryState(q);
    },
    [setPage],
  );

  const setSort = useCallback(
    (next: string) => {
      setPage(1);
      setSortState(next);
    },
    [setPage],
  );

  const setVisibleColumns = useCallback((next: Set<C>) => {
    // Keep at least one column visible — ignore an empty set.
    if (next.size === 0) return;
    setVisibleColumnsState(next);
  }, []);

  const isColumnVisible = useCallback(
    (key: C) => visibleColumns.has(key),
    [visibleColumns],
  );

  // Single-expand: opening a row collapses any other open row, so the fixed
  // viewport never has to juggle multiple drawers.
  const toggleExpanded = useCallback((id: string) => {
    setExpanded((prev) => (prev.has(id) ? new Set() : new Set([id])));
  }, []);

  const isExpanded = useCallback((id: string) => expanded.has(id), [expanded]);

  const collapse = useCallback(() => {
    setExpanded((prev) => (prev.size === 0 ? prev : new Set()));
  }, []);

  return {
    query,
    setQuery,
    page,
    setPage,
    sort,
    setSort,
    visibleColumns,
    setVisibleColumns,
    isColumnVisible,
    expanded,
    toggleExpanded,
    isExpanded,
    collapse,
    resetPage,
  };
}
