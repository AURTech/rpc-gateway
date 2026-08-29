"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  ChevronRight,
  LoaderCircle,
  RefreshCw,
  Settings2,
  Trash2,
} from "lucide-react";
import { AnimatePresence } from "motion/react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import {
  RPC_PROVIDER_SYNC_STATUSES,
  RPC_PROVIDER_VENDORS,
  type RpcProviderSyncStatus,
  type RpcProviderVendor,
} from "@/api/providers/client";
import { TableDisclosureMotion } from "@/components/patterns/table-disclosure-motion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableExpandedRow,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TableColumnFilter } from "@/components/ui/table-column-filter";
import { TablePagination } from "@/components/ui/table-pagination";
import {
  TableEmptyRow,
  TableErrorRow,
  TableLoadingRows,
} from "@/components/ui/table-states";
import { TableColumnsHead } from "@/components/ui/table-toolbar";
import { Time } from "@/components/ui/time";
import { useInitialTableRowEntrance } from "@/hooks/use-initial-table-row-entrance";
import { useTableController } from "@/hooks/use-table-controller";
import { usePathname, useRouter } from "@/i18n/navigation";
import { ConnectProviderButton } from "./connect-provider-button";
import { DeleteProviderDialog } from "./delete-provider-dialog";
import {
  endpointCounts,
  type ProviderRecord,
  providerStatus,
} from "./provider-model";
import { ProviderNetworkIconGroup } from "./provider-network-visuals";
import { ProviderRowExpansion } from "./provider-row-expansion";
import { ProviderSettingsDialog } from "./provider-settings";
import { ProviderSyncDialog } from "./provider-sync-dialog";
import {
  useProviderRun,
  useProviders,
  useStartProviderSync,
} from "./use-providers";

const PAGE_SIZE = 12;
const PROVIDER_OPTIONAL_COLUMNS = [
  "networks",
  "endpoints",
  "syncStatus",
  "lastSync",
] as const;
type ProviderColumnKey = (typeof PROVIDER_OPTIONAL_COLUMNS)[number];

function ProviderRow({
  provider,
  expanded,
  onToggleExpanded,
  onEdit,
  onDelete,
  enterIndex,
  visibleColumns,
  colSpan,
}: {
  provider: ProviderRecord;
  expanded: boolean;
  onToggleExpanded: () => void;
  onEdit: () => void;
  onDelete: () => void;
  enterIndex?: number;
  visibleColumns: Set<ProviderColumnKey>;
  colSpan: number;
}) {
  const t = useTranslations("dashboard.endpointProviders");
  const queryClient = useQueryClient();
  const sync = useStartProviderSync(provider.id);
  const [syncOpen, setSyncOpen] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const runQuery = useProviderRun(provider.id, runId);
  const completedRun = useRef<string | null>(null);
  const syncDialogOpenRef = useRef(false);
  const counts = endpointCounts(provider);
  const status = providerStatus(provider);
  const expansionId = `provider-${provider.id}-details`;
  const [disclosurePresent, setDisclosurePresent] = useState(expanded);

  useEffect(() => {
    if (expanded) setDisclosurePresent(true);
  }, [expanded]);

  useEffect(() => {
    const run = runQuery.data;
    if (
      !run ||
      run.state === "queued" ||
      run.state === "running" ||
      completedRun.current === run.id
    ) {
      return;
    }
    completedRun.current = run.id;
    queryClient.invalidateQueries({ queryKey: ["providers"] });
    queryClient.invalidateQueries({ queryKey: ["endpoints"] });
  }, [queryClient, runQuery.data]);

  function startSync() {
    sync.reset();
    setRunId(null);
    syncDialogOpenRef.current = true;
    setSyncOpen(true);
    sync.mutate(undefined, {
      onSuccess: (run) => {
        if (syncDialogOpenRef.current) setRunId(run.id);
      },
    });
  }

  function setSyncDialogOpen(open: boolean) {
    syncDialogOpenRef.current = open;
    setSyncOpen(open);
    if (open) return;
    setRunId(null);
    sync.reset();
  }

  const syncRun = runQuery.data ?? sync.data ?? null;
  const endpointTotal = counts.present + counts.missing;

  return (
    <>
      <TableRow
        expanded={expanded}
        enterIndex={enterIndex}
        data-disclosure-closing={
          !expanded && disclosurePresent ? "true" : undefined
        }
      >
        <TableCell className="min-w-0 overflow-hidden">
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls={expanded ? expansionId : undefined}
            onClick={onToggleExpanded}
            className="group/link flex w-full min-w-0 items-center gap-2 rounded-sm text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
          >
            <ChevronRight
              className="table-disclosure-chevron size-4 shrink-0 text-ink-400"
              aria-hidden
            />
            <span className="min-w-0 flex-1">
              <span className="block truncate font-semibold text-ink-900 group-hover/link:text-brand">
                {provider.name}
              </span>
              <span className="block truncate text-xs text-ink-500">
                {t(`onboarding.vendors.${provider.vendor}`)}
              </span>
            </span>
          </button>
        </TableCell>
        {visibleColumns.has("networks") ? (
          <TableCell>
            <ProviderNetworkIconGroup
              networks={provider.networks}
              vendor={provider.vendor}
            />
          </TableCell>
        ) : null}
        {visibleColumns.has("endpoints") ? (
          <TableCell>
            <span className="flex items-center gap-2 whitespace-nowrap">
              <span className="font-semibold tabular-nums text-ink-900">
                {endpointTotal}
              </span>
              {counts.missing > 0 ? (
                <Badge variant="warning">
                  {t("endpoints.missing", { count: counts.missing })}
                </Badge>
              ) : null}
            </span>
          </TableCell>
        ) : null}
        {visibleColumns.has("syncStatus") ? (
          <TableCell>
            <Badge
              variant={
                status === "syncing"
                  ? "brand"
                  : provider.last_sync_status === "success"
                    ? "positive"
                    : provider.last_sync_status === "partial" ||
                        provider.last_sync_status === "failed"
                      ? "warning"
                      : "neutral"
              }
            >
              {status === "syncing"
                ? t("status.syncing")
                : t(`filters.results.${provider.last_sync_status}`)}
            </Badge>
          </TableCell>
        ) : null}
        {visibleColumns.has("lastSync") ? (
          <TableCell>
            {provider.last_sync_at ? (
              <span className="whitespace-nowrap text-xs text-ink-500">
                <Time value={provider.last_sync_at} />
              </span>
            ) : (
              <span className="text-ink-400">—</span>
            )}
          </TableCell>
        ) : null}
        <TableCell align="right">
          <div className="flex justify-end gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={t("actions.sync")}
              disabled={
                !provider.enabled || sync.isPending || status === "syncing"
              }
              onClick={startSync}
            >
              {sync.isPending || status === "syncing" ? (
                <LoaderCircle className="animate-spin" aria-hidden />
              ) : (
                <RefreshCw aria-hidden />
              )}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={t("actions.settings")}
              onClick={onEdit}
            >
              <Settings2 aria-hidden />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="text-ink-500 hover:bg-danger-soft hover:text-danger"
              aria-label={t("actions.delete")}
              onClick={onDelete}
            >
              <Trash2 aria-hidden />
            </Button>
          </div>
        </TableCell>
      </TableRow>
      <ProviderSyncDialog
        providerName={provider.name}
        open={syncOpen}
        run={syncRun}
        starting={sync.isPending}
        startError={sync.isError ? sync.error.message : null}
        statusError={runQuery.isError}
        onOpenChange={setSyncDialogOpen}
        onRetryStart={startSync}
        onRetryStatus={() => runQuery.refetch()}
      />
      <AnimatePresence
        initial={false}
        onExitComplete={() => setDisclosurePresent(false)}
      >
        {expanded ? (
          <TableExpandedRow
            key={expansionId}
            id={expansionId}
            colSpan={colSpan}
          >
            <TableDisclosureMotion>
              <div className="px-8 py-7">
                <ProviderRowExpansion provider={provider} />
              </div>
            </TableDisclosureMotion>
          </TableExpandedRow>
        ) : null}
      </AnimatePresence>
    </>
  );
}

export function ProvidersTable({
  onActiveRunsChange,
}: {
  onActiveRunsChange?: (count: number) => void;
}) {
  const t = useTranslations("dashboard.endpointProviders");
  const queryClient = useQueryClient();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams() ?? new URLSearchParams();
  const page = Math.max(1, Number(searchParams.get("providerPage")) || 1);
  const q = searchParams.get("providerQ") ?? "";
  const vendor = (searchParams.get("providerVendor") ?? "all") as
    | "all"
    | RpcProviderVendor;
  const result = (searchParams.get("providerResult") ?? "all") as
    | "all"
    | RpcProviderSyncStatus;
  const settingsId = searchParams.get("providerSettings");
  const [expandedId, setExpandedId] = useState<string | null>(
    searchParams.get("expandedProvider"),
  );
  const [deletingProvider, setDeletingProvider] =
    useState<ProviderRecord | null>(null);
  const columns = useTableController<ProviderColumnKey>({
    allColumns: PROVIDER_OPTIONAL_COLUMNS,
  });
  const query = useProviders({
    page,
    size: PAGE_SIZE,
    ...(q ? { q } : {}),
    ...(vendor !== "all" ? { vendor } : {}),
    ...(result !== "all" ? { last_sync_status: result } : {}),
  });
  const animateInitialRows = useInitialTableRowEntrance(
    !query.isLoading && !query.isError,
  );
  // The settings dialog is driven by the URL alone: deriving it keeps a close
  // from racing the async `router.replace` that clears `providerSettings`.
  const editingProvider = settingsId
    ? ((query.data?.items.find((item) => item.id === settingsId) as
        | ProviderRecord
        | undefined) ?? null)
    : null;
  const activeRuns =
    query.data?.items.filter((provider) => provider.syncing).length ?? 0;
  const previousActiveRuns = useRef(activeRuns);

  useEffect(() => {
    onActiveRunsChange?.(activeRuns);
    if (previousActiveRuns.current > 0 && activeRuns === 0) {
      queryClient.invalidateQueries({ queryKey: ["endpoints"] });
    }
    previousActiveRuns.current = activeRuns;
  }, [activeRuns, onActiveRunsChange, queryClient]);

  useEffect(
    () => () => {
      onActiveRunsChange?.(0);
    },
    [onActiveRunsChange],
  );

  const replaceParams = (updates: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(updates)) {
      if (!value || value === "all") next.delete(key);
      else next.set(key, value);
    }
    if ("expandedProvider" in updates && !updates.expandedProvider) {
      setExpandedId(null);
    }
    const nextQuery = next.toString();
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, {
      scroll: false,
    });
  };

  const setExpanded = (id: string | null) => {
    setExpandedId(id);
    const next = new URLSearchParams(searchParams.toString());
    if (id) next.set("expandedProvider", id);
    else next.delete("expandedProvider");
    const nextQuery = next.toString();
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, {
      scroll: false,
    });
  };

  const setEditing = (provider: ProviderRecord | null) => {
    const next = new URLSearchParams(searchParams.toString());
    if (provider) next.set("providerSettings", provider.id);
    else next.delete("providerSettings");
    const nextQuery = next.toString();
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, {
      scroll: false,
    });
  };

  const clearFilters = () => {
    replaceParams({
      providerQ: null,
      providerPage: null,
      providerVendor: null,
      providerResult: null,
      expandedProvider: null,
    });
    setExpandedId(null);
  };
  const hasFilter = Boolean(q || vendor !== "all" || result !== "all");
  const columnLabels: Record<ProviderColumnKey, string> = {
    networks: t("columns.networks"),
    endpoints: t("columns.endpoints"),
    syncStatus: t("columns.syncStatus"),
    lastSync: t("columns.lastSync"),
  };
  const providerColumnLabel =
    vendor === "all"
      ? t("columns.provider")
      : `${t("columns.provider")} · ${t(`onboarding.vendors.${vendor}`)}`;
  const syncStatusColumnLabel =
    result === "all"
      ? t("columns.syncStatus")
      : `${t("columns.syncStatus")} · ${t(`filters.results.${result}`)}`;
  const columnCount = columns.visibleColumns.size + 2;

  return (
    <section aria-label={t("list.ariaLabel")} className="min-w-0 space-y-5">
      <Table
        rowSpotlight
        className="table-fixed"
        containerClassName="shadow-section"
        scrollClassName="h-table-viewport-12"
        footer={
          query.data && query.data.total > 0 ? (
            <div className="bg-table-frame px-4 py-3">
              <TablePagination
                page={query.data.page}
                maxPage={query.data.max_page}
                pageSize={query.data.size}
                pageItemCount={query.data.items.length}
                total={query.data.total}
                onPageChange={(nextPage) =>
                  replaceParams({
                    providerPage: nextPage > 1 ? String(nextPage) : null,
                    expandedProvider: null,
                  })
                }
                rangeLabel={({ from, to, total }) =>
                  t("list.range", { from, to, total })
                }
                prevLabel={t("list.previous")}
                nextLabel={t("list.next")}
              />
            </div>
          ) : null
        }
      >
        <colgroup>
          <col className="w-64" />
          {columns.isColumnVisible("networks") ? <col /> : null}
          {columns.isColumnVisible("endpoints") ? (
            <col className="w-36" />
          ) : null}
          {columns.isColumnVisible("syncStatus") ? (
            <col className="w-36" />
          ) : null}
          {columns.isColumnVisible("lastSync") ? (
            <col className="w-40" />
          ) : null}
          <col className="w-32" />
        </colgroup>
        <TableHeader>
          <TableRow>
            <TableHead>
              <TableColumnFilter
                label={providerColumnLabel}
                active={vendor !== "all"}
              >
                <DropdownMenuRadioGroup
                  value={vendor}
                  onValueChange={(value) =>
                    replaceParams({
                      providerVendor: value,
                      providerPage: null,
                      expandedProvider: null,
                    })
                  }
                >
                  <DropdownMenuRadioItem value="all">
                    {t("filters.allVendors")}
                  </DropdownMenuRadioItem>
                  {RPC_PROVIDER_VENDORS.map((item) => (
                    <DropdownMenuRadioItem key={item} value={item}>
                      {t(`onboarding.vendors.${item}`)}
                    </DropdownMenuRadioItem>
                  ))}
                </DropdownMenuRadioGroup>
              </TableColumnFilter>
            </TableHead>
            {columns.isColumnVisible("networks") ? (
              <TableHead>{t("columns.networks")}</TableHead>
            ) : null}
            {columns.isColumnVisible("endpoints") ? (
              <TableHead>{t("columns.endpoints")}</TableHead>
            ) : null}
            {columns.isColumnVisible("syncStatus") ? (
              <TableHead>
                <TableColumnFilter
                  label={syncStatusColumnLabel}
                  active={result !== "all"}
                >
                  <DropdownMenuRadioGroup
                    value={result}
                    onValueChange={(value) =>
                      replaceParams({
                        providerResult: value,
                        providerPage: null,
                        expandedProvider: null,
                      })
                    }
                  >
                    <DropdownMenuRadioItem value="all">
                      {t("filters.allResults")}
                    </DropdownMenuRadioItem>
                    {RPC_PROVIDER_SYNC_STATUSES.map((item) => (
                      <DropdownMenuRadioItem key={item} value={item}>
                        {t(`filters.results.${item}`)}
                      </DropdownMenuRadioItem>
                    ))}
                  </DropdownMenuRadioGroup>
                </TableColumnFilter>
              </TableHead>
            ) : null}
            {columns.isColumnVisible("lastSync") ? (
              <TableHead>{t("columns.lastSync")}</TableHead>
            ) : null}
            <TableColumnsHead
              label={t("columnsLabel")}
              columns={PROVIDER_OPTIONAL_COLUMNS}
              labels={columnLabels}
              value={columns.visibleColumns}
              onValueChange={columns.setVisibleColumns}
            />
          </TableRow>
        </TableHeader>
        <TableBody refreshing={query.isPlaceholderData}>
          {query.isLoading ? (
            <TableLoadingRows colSpan={columnCount} rows={PAGE_SIZE} />
          ) : query.isError ? (
            <TableErrorRow
              colSpan={columnCount}
              title={t("error.title")}
              body={t("error.body")}
              retry={t("error.retry")}
              onRetry={() => query.refetch()}
            />
          ) : query.data?.items.length ? (
            query.data.items.map((provider, index) => (
              <ProviderRow
                key={provider.id}
                provider={provider as ProviderRecord}
                expanded={expandedId === provider.id}
                onToggleExpanded={() =>
                  setExpanded(expandedId === provider.id ? null : provider.id)
                }
                onEdit={() => setEditing(provider as ProviderRecord)}
                onDelete={() => setDeletingProvider(provider as ProviderRecord)}
                enterIndex={animateInitialRows ? index : undefined}
                visibleColumns={columns.visibleColumns}
                colSpan={columnCount}
              />
            ))
          ) : (
            <TableEmptyRow
              colSpan={columnCount}
              hasFilter={hasFilter}
              cellClassName="h-table-body-12"
              empty={{
                title: t("empty.title"),
                body: t("empty.body"),
                cta: t("empty.cta"),
                action: (
                  <ConnectProviderButton
                    label={t("empty.cta")}
                    size="sm"
                    variant="soft"
                  />
                ),
              }}
              filtered={{
                title: t("filtered.title"),
                body: t("filtered.body"),
                cta: t("filtered.cta"),
              }}
              onClear={clearFilters}
            />
          )}
        </TableBody>
      </Table>

      <ProviderSettingsDialog
        provider={editingProvider}
        open={editingProvider !== null}
        onOpenChange={(open) => {
          if (!open) setEditing(null);
        }}
      />

      <DeleteProviderDialog
        provider={deletingProvider}
        open={deletingProvider !== null}
        onOpenChange={(open) => {
          if (!open) setDeletingProvider(null);
        }}
        onRemoved={(id) => {
          if (expandedId === id) setExpanded(null);
          setDeletingProvider(null);
        }}
      />
    </section>
  );
}
