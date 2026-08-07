"use client";

import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import {
  ACCOUNT_STATUSES,
  type AccountStatus,
  type ListAccountsParams,
} from "@/api/accounts/client";
import {
  FilterDrawer,
  FilterSingleGroup,
} from "@/components/patterns/filter-drawer";
import { ResponsiveListView } from "@/components/patterns/responsive-list-view";
import { TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ColumnsToggle, HeaderFilter } from "@/components/ui/table-toolbar";
import {
  useAccountsInfiniteQuery,
  useAccountsQuery,
} from "@/hooks/use-accounts";
import { useIsDesktop } from "@/hooks/use-media-query";
import { useSheetDetail } from "@/hooks/use-sheet-detail";
import { useTableController } from "@/hooks/use-table-controller";

import { AccountCard } from "./account-card";
import { AccountDetailDrawer } from "./account-detail-drawer";
import { AccountRow } from "./account-row";

const ACCOUNT_PAGE_SIZE = 10;

export type AccountColumnKey = "email" | "role" | "status" | "created";
const ALL_ACCOUNT_COLUMNS: readonly AccountColumnKey[] = [
  "email",
  "role",
  "status",
  "created",
];

type StatusFilter = "all" | AccountStatus;
const STATUS_FILTER_OPTIONS: readonly StatusFilter[] = [
  "all",
  ...ACCOUNT_STATUSES,
];

export function AccountsContent() {
  const t = useTranslations("dashboard.admin.accounts");
  const isDesktop = useIsDesktop();

  const table = useTableController<AccountColumnKey>({
    allColumns: ALL_ACCOUNT_COLUMNS,
  });
  const { page, setPage } = table;

  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  // Shared filter params (no `page`) for both the desktop pager query and the
  // mobile infinite query.
  const baseFilters: Omit<ListAccountsParams, "page"> = useMemo(
    () => ({
      size: ACCOUNT_PAGE_SIZE,
      status: statusFilter === "all" ? undefined : statusFilter,
    }),
    [statusFilter],
  );

  const desktopQuery = useAccountsQuery(
    { ...baseFilters, page },
    { enabled: isDesktop },
  );
  const infiniteQuery = useAccountsInfiniteQuery(baseFilters, {
    enabled: !isDesktop,
  });

  const data = desktopQuery.data;

  // Clamp the page when the result set shrinks under us (desktop pager only).
  useEffect(() => {
    if (!data) return;
    if (data.max_page === 0 && page !== 1) setPage(1);
    else if (data.max_page > 0 && page > data.max_page) setPage(data.max_page);
  }, [data, page, setPage]);

  const listIsLoading = isDesktop
    ? desktopQuery.isLoading
    : infiniteQuery.isLoading;
  const listIsError = isDesktop ? desktopQuery.isError : infiniteQuery.isError;
  const items = isDesktop
    ? (data?.items ?? [])
    : (infiniteQuery.data?.pages.flatMap((p) => p.items) ?? []);

  const detail = useSheetDetail(items, (account) => account.id);

  const filterCount = statusFilter !== "all" ? 1 : 0;
  const hasActiveFilter = filterCount > 0;

  const clearFilters = () => {
    table.resetPage();
    setStatusFilter("all");
  };

  const statusLabels: Record<StatusFilter, string> = {
    all: t("filters.statusAll"),
    unactivated: t("status.unactivated"),
    active: t("status.active"),
    disabled: t("status.disabled"),
    archived: t("status.archived"),
  };
  const columnLabels: Record<AccountColumnKey, string> = {
    email: t("table.email"),
    role: t("table.role"),
    status: t("table.status"),
    created: t("table.created"),
  };

  const tableHeader = (
    <TableHeader>
      <TableRow>
        {table.isColumnVisible("email") ? (
          <TableHead>{t("table.email")}</TableHead>
        ) : null}
        {table.isColumnVisible("role") ? (
          <TableHead>{t("table.role")}</TableHead>
        ) : null}
        {table.isColumnVisible("status") ? (
          <TableHead>
            <HeaderFilter
              label={t("table.status")}
              options={STATUS_FILTER_OPTIONS}
              optionLabels={statusLabels}
              value={statusFilter}
              onValueChange={(next) => {
                table.resetPage();
                setStatusFilter(next);
              }}
            />
          </TableHead>
        ) : null}
        {table.isColumnVisible("created") ? (
          <TableHead>{t("table.created")}</TableHead>
        ) : null}
        <TableHead align="right">
          <ColumnsToggle
            label={t("table.columnsLabel")}
            columns={ALL_ACCOUNT_COLUMNS}
            labels={columnLabels}
            value={table.visibleColumns}
            onValueChange={table.setVisibleColumns}
          />
        </TableHead>
      </TableRow>
    </TableHeader>
  );

  return (
    <>
      <ResponsiveListView
        items={items}
        getKey={(account) => account.id}
        isLoading={listIsLoading}
        isError={listIsError}
        table={table}
        tableHeader={tableHeader}
        renderRow={(account) => (
          <AccountRow
            key={account.id}
            account={account}
            visibleColumns={table.visibleColumns}
            selected={detail.isSelected(account.id)}
            onSelect={detail.toggle}
          />
        )}
        renderCard={(account) => (
          <AccountCard
            account={account}
            selected={detail.isSelected(account.id)}
            onSelect={detail.toggle}
          />
        )}
        infinite={{
          hasMore: infiniteQuery.hasNextPage,
          isFetchingMore: infiniteQuery.isFetchingNextPage,
          onLoadMore: () => {
            infiniteQuery.fetchNextPage();
          },
        }}
        filter={
          // Desktop filters live in the Status header; only the mobile card
          // list needs the bundled filter drawer.
          isDesktop ? null : (
            <FilterDrawer
              label={t("filters.title")}
              title={t("filters.title")}
              activeCount={filterCount}
              onReset={clearFilters}
              resetLabel={t("filteredEmpty.cta")}
              doneLabel={t("filters.done")}
            >
              <FilterSingleGroup
                label={t("table.status")}
                options={STATUS_FILTER_OPTIONS}
                optionLabels={statusLabels}
                value={statusFilter}
                onValueChange={(next) => {
                  table.resetPage();
                  setStatusFilter(next);
                }}
              />
            </FilterDrawer>
          )
        }
        pagination={{
          page: data?.page ?? page,
          maxPage: Math.max(1, data?.max_page ?? 1),
          pageSize: ACCOUNT_PAGE_SIZE,
          pageItemCount: data?.items.length ?? items.length,
          total: data?.total ?? items.length,
          onPageChange: setPage,
          rangeLabel: (args) => t("table.range", args),
          prevLabel: t("table.prev"),
          nextLabel: t("table.next"),
        }}
        states={{
          hasActiveFilter,
          onClearFilter: clearFilters,
          onRetry: () =>
            isDesktop ? desktopQuery.refetch() : infiniteQuery.refetch(),
          empty: {
            title: t("empty.title"),
            body: t("empty.body"),
            cta: t("empty.cta"),
          },
          filtered: {
            title: t("filteredEmpty.title"),
            body: t("filteredEmpty.body"),
            cta: t("filteredEmpty.cta"),
          },
          error: {
            title: t("error.title"),
            body: t("error.body"),
            retry: t("error.retry"),
          },
        }}
      />

      <AccountDetailDrawer
        account={detail.selected}
        open={detail.open}
        onOpenChange={detail.onOpenChange}
      />
    </>
  );
}
