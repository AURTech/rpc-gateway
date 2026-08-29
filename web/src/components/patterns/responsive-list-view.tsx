"use client";

import type * as React from "react";

import { MobileDataList } from "@/components/patterns/mobile-data-list";
import { Table, TableBody } from "@/components/ui/table";
import {
  TablePagination,
  TablePaginationSkeleton,
} from "@/components/ui/table-pagination";
import {
  TABLE_VIEWPORT_ROWS,
  type TableEmptyCopy,
  TableEmptyRow,
  TableErrorRow,
  TableFillerRows,
  TableLoadingHeader,
  TableLoadingRows,
} from "@/components/ui/table-states";
import { Toolbar, ToolbarGroup } from "@/components/ui/toolbar";
import { useInitialTableRowEntrance } from "@/hooks/use-initial-table-row-entrance";
import { useIsDesktop } from "@/hooks/use-media-query";
import type { TableController } from "@/hooks/use-table-controller";
import { Link } from "@/i18n/navigation";

/**
 * Responsive list shell shared by every list page. Owns the cross-cutting glue
 * that used to be hand-wired in each `*-content.tsx`:
 *  - the desktop `<Table>` / mobile `<MobileDataList>` breakpoint branch;
 *  - loading / error / empty rendering for BOTH views from one copy config
 *    (table `<tr>` states + mobile `<div>` states);
 *  - the pagination footer (desktop) and infinite-scroll wiring (mobile);
 *  - the filter + action toolbar.
 *
 * The page supplies only what genuinely differs: the `<TableHeader>` (with its
 * header filters / column toggle), `renderRow`, `renderCard`, the (pre-gated)
 * filter node, and the toolbar action. Per-row local state (dialogs, mutations)
 * stays inside the row / card components — the shell never owns it. Takes
 * strings / nodes only; no `next-intl`, no hardcoded copy.
 */
export type ResponsiveListViewProps<T, C extends string> = {
  // Data / async state.
  items: readonly T[];
  getKey: (item: T) => string;
  isLoading?: boolean;
  isError?: boolean;
  isRefreshing?: boolean;

  // Desktop table — page owns the header + row; the shell owns state rows.
  table: TableController<C>;
  tableHeader: React.ReactNode;
  /** `enterIndex` is present only for the first settled desktop dataset. */
  renderRow: (item: T, enterIndex?: number) => React.ReactNode;
  /** Columns beyond `visibleColumns` for colSpan; default 1 (Action column). */
  extraColSpan?: number;

  // Mobile card list (infinite scroll).
  renderCard: (item: T) => React.ReactNode;
  loadingRows?: number;
  infinite?: {
    hasMore: boolean;
    isFetchingMore: boolean;
    onLoadMore: () => void;
  };

  // Toolbar (all optional; nothing rendered when all omitted).
  /** Filter surface, pre-gated by the page (e.g. `!isDesktop ? <FilterDrawer/> : null`). */
  filter?: React.ReactNode;
  /** Right-aligned action, e.g. a "New …" button. */
  toolbarEnd?: React.ReactNode;
  toolbarClassName?: string;

  // Pagination — desktop footer only (mobile uses `infinite`). Omit for none.
  pagination?: {
    page: number;
    maxPage: number;
    pageSize: number;
    pageItemCount: number;
    total: number;
    onPageChange: (next: number) => void;
    rangeLabel: (args: { from: number; to: number; total: number }) => string;
    prevLabel: string;
    nextLabel: string;
  };

  // Empty / error copy, shared by the table <tr> states and mobile <div> states.
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

export function ResponsiveListView<T, C extends string>({
  items,
  getKey,
  isLoading = false,
  isError = false,
  isRefreshing = false,
  table,
  tableHeader,
  renderRow,
  extraColSpan = 1,
  renderCard,
  loadingRows,
  infinite,
  filter,
  toolbarEnd,
  toolbarClassName,
  pagination,
  states,
}: ResponsiveListViewProps<T, C>) {
  const isDesktop = useIsDesktop();
  const animateInitialRows = useInitialTableRowEntrance(
    isDesktop && !isLoading && !isError,
  );
  const colSpan = table.visibleColumns.size + extraColSpan;
  const filtered = states.filtered ?? states.empty;

  const footer = !pagination ? null : isLoading ? (
    <div className="px-4 py-3">
      <TablePaginationSkeleton />
    </div>
  ) : !isError && items.length > 0 ? (
    <div className="px-4 py-3">
      <TablePagination
        page={pagination.page}
        maxPage={pagination.maxPage}
        pageSize={pagination.pageSize}
        pageItemCount={pagination.pageItemCount}
        total={pagination.total}
        onPageChange={pagination.onPageChange}
        rangeLabel={pagination.rangeLabel}
        prevLabel={pagination.prevLabel}
        nextLabel={pagination.nextLabel}
      />
    </div>
  ) : null;

  const emptyNode = (
    <div className="mx-auto flex max-w-prose-narrow flex-col items-center gap-2 text-center">
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
      ) : states.empty.href ? (
        <Link
          href={states.empty.href}
          className="mt-2 inline-flex h-9 items-center rounded-md bg-brand-soft px-4 text-sm font-semibold text-brand transition-colors hover:bg-brand hover:text-white"
        >
          {states.empty.cta}
        </Link>
      ) : null}
    </div>
  );

  const errorNode = (
    <div
      role="alert"
      className="mx-auto flex max-w-prose-narrow flex-col items-center gap-2 text-center"
    >
      <p className="text-lg font-semibold text-ink-900">{states.error.title}</p>
      <p className="text-md text-ink-500">{states.error.body}</p>
      <button
        type="button"
        onClick={states.onRetry}
        className="mt-2 inline-flex h-9 items-center rounded-md bg-brand-soft px-4 text-sm font-semibold text-brand transition-colors hover:bg-brand hover:text-white"
      >
        {states.error.retry}
      </button>
    </div>
  );

  const showToolbar = filter || toolbarEnd;

  return (
    <div className="flex flex-col gap-3">
      {showToolbar ? (
        <Toolbar className={toolbarClassName}>
          <ToolbarGroup>{filter}</ToolbarGroup>
          {toolbarEnd ? <ToolbarGroup>{toolbarEnd}</ToolbarGroup> : null}
        </Toolbar>
      ) : null}

      {isDesktop ? (
        <Table footer={footer}>
          {isLoading ? <TableLoadingHeader colSpan={colSpan} /> : tableHeader}
          <TableBody refreshing={isRefreshing}>
            {isLoading ? (
              <TableLoadingRows
                colSpan={colSpan}
                rows={loadingRows ?? TABLE_VIEWPORT_ROWS}
              />
            ) : null}
            {!isLoading && isError ? (
              <TableErrorRow
                colSpan={colSpan}
                title={states.error.title}
                body={states.error.body}
                retry={states.error.retry}
                onRetry={states.onRetry}
              />
            ) : null}
            {!isLoading && !isError && items.length === 0 ? (
              <TableEmptyRow
                colSpan={colSpan}
                hasFilter={states.hasActiveFilter}
                empty={states.empty}
                filtered={filtered}
                onClear={states.onClearFilter}
              />
            ) : null}
            {!isLoading && !isError && items.length > 0 ? (
              <>
                {items.map((item, index) =>
                  renderRow(item, animateInitialRows ? index : undefined),
                )}
                <TableFillerRows
                  count={TABLE_VIEWPORT_ROWS - items.length}
                  colSpan={colSpan}
                />
              </>
            ) : null}
          </TableBody>
        </Table>
      ) : (
        <MobileDataList
          items={items}
          getKey={getKey}
          isLoading={isLoading}
          isError={isError}
          empty={emptyNode}
          error={errorNode}
          loadingRows={loadingRows}
          infinite={infinite}
          renderCard={renderCard}
        />
      )}
    </div>
  );
}
