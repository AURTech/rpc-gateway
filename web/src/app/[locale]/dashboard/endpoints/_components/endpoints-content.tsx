"use client";

import {
  keepPreviousData,
  useInfiniteQuery,
  useQuery,
} from "@tanstack/react-query";
import { XIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { type Dispatch, type SetStateAction, useMemo, useState } from "react";
import { toast } from "sonner";

import { isApiError } from "@/api/client";
import {
  type Endpoint,
  type EndpointOriginType,
  type ListEndpointsParams,
  listEndpoints,
} from "@/api/endpoints/client";
import {
  FilterDrawer,
  FilterMultiGroup,
  FilterSingleGroup,
} from "@/components/patterns/filter-drawer";
import { ResponsiveListView } from "@/components/patterns/responsive-list-view";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChainIcon } from "@/components/ui/chain-icon";
import { Checkbox } from "@/components/ui/checkbox";
import { TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  ColumnsToggle,
  HeaderFilter,
  MultiHeaderFilter,
} from "@/components/ui/table-toolbar";
import { useUpdateEndpointMutation } from "@/hooks/use-endpoints";
import { useIsDesktop } from "@/hooks/use-media-query";
import { useProviderQuery } from "@/hooks/use-providers";
import { useSheetDetail } from "@/hooks/use-sheet-detail";
import { useTableController } from "@/hooks/use-table-controller";
import { CHAINS, type Chain, NETWORKS, type Network } from "@/lib/blockchain";

import { BulkDeleteEndpointsDialog } from "./bulk-delete-endpoints-dialog";
import { DeleteEndpointDialog } from "./delete-endpoint-dialog";
import { EditEndpointSheet } from "./edit-endpoint-sheet";
import { EndpointAuditDialog } from "./endpoint-audit-dialog";
import { EndpointCard } from "./endpoint-card";
import { EndpointDetailSheet } from "./endpoint-detail-sheet";
import { EndpointRow } from "./endpoint-row";

const ENDPOINT_PAGE_SIZE = 12;
const PROVIDERS_HREF = "/dashboard/providers";

export type EndpointColumnKey =
  | "name"
  | "chain"
  | "network"
  | "protocol"
  | "origin"
  | "state";

// Manual endpoints are all one origin, so the source column is dropped;
// provider endpoints keep it to surface which provider owns each row.
const MANUAL_COLUMNS: readonly EndpointColumnKey[] = [
  "name",
  "chain",
  "network",
  "protocol",
  "state",
];
const PROVIDER_COLUMNS: readonly EndpointColumnKey[] = [
  "name",
  "chain",
  "network",
  "protocol",
  "origin",
  "state",
];

type StateFilter = "all" | "true" | "false";

const STATE_OPTIONS: readonly StateFilter[] = ["all", "true", "false"];

/** Shared filter params (no `page`) for both the desktop pager and mobile
 *  infinite query. Origin is fixed by the active tab; chain/network are
 *  multi-select; state single-select. All protocols are listed together.
 *  `provider` scopes the provider tab to one provider (deep link only). */
function buildBaseFilters(
  origin: EndpointOriginType,
  chain: readonly Chain[],
  network: readonly Network[],
  state: StateFilter,
  provider: string | null,
): Omit<ListEndpointsParams, "page"> {
  const f: Omit<ListEndpointsParams, "page"> = {
    size: ENDPOINT_PAGE_SIZE,
    origin_type: origin,
  };
  if (chain.length > 0) f.chain = [...chain];
  if (network.length > 0) f.network = [...network];
  if (state !== "all") f.enabled = state === "true";
  if (provider) f.provider_id = provider;
  return f;
}

/**
 * An origin-scoped endpoint table. Rendered once per tab: `origin="manual"`
 * (self-created, full CRUD) and `origin="provider"` (provider-synced,
 * connection is read-only; the source column shows the owning provider and its
 * sync status). Desktop is a `<Table>` with in-header filters — multi-select
 * chain / network (chain options carry their logo) and single-select state — a
 * column toggle, and numbered pagination; narrow viewports fall back
 * to {@link EndpointCard} with infinite scroll and a filter drawer. Backed by
 * `/v2/endpoints`.
 *
 * `providerId` narrows the provider tab to a single provider's inventory. It
 * arrives from a deep link rather than the toolbar, so it is surfaced as a
 * dismissible chip — an unexplained pre-filtered table reads as missing rows.
 */
export function EndpointsContent({
  origin,
  providerId = null,
  onClearProvider,
  selectedById,
  setSelectedById,
  bulkDeleteOpen,
  onBulkDeleteOpenChange,
}: {
  origin: EndpointOriginType;
  providerId?: string | null;
  onClearProvider?: () => void;
  selectedById: ReadonlyMap<string, Endpoint>;
  setSelectedById: Dispatch<SetStateAction<Map<string, Endpoint>>>;
  bulkDeleteOpen: boolean;
  onBulkDeleteOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("dashboard.endpoints");
  const isDesktop = useIsDesktop();
  const isProvider = origin === "provider";
  const columns = isProvider ? PROVIDER_COLUMNS : MANUAL_COLUMNS;
  const providerQuery = useProviderQuery(providerId);

  const table = useTableController<EndpointColumnKey>({
    allColumns: columns,
  });
  const [chainFilter, setChainFilter] = useState<readonly Chain[]>(() => []);
  const [networkFilter, setNetworkFilter] = useState<readonly Network[]>(
    () => [],
  );
  const [stateFilter, setStateFilter] = useState<StateFilter>("all");
  const [editTarget, setEditTarget] = useState<Endpoint | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Endpoint | null>(null);
  const [auditTarget, setAuditTarget] = useState<Endpoint | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const updateMutation = useUpdateEndpointMutation();

  const { page, setPage } = table;

  const baseFilters = useMemo(
    () =>
      buildBaseFilters(
        origin,
        chainFilter,
        networkFilter,
        stateFilter,
        providerId,
      ),
    [origin, chainFilter, networkFilter, stateFilter, providerId],
  );

  // Desktop: page-based query feeding the numbered pager, with out-of-range
  // page self-correction (mirrors the Nodes / gateways tables).
  const {
    data,
    isLoading: deskLoading,
    isError: deskError,
    refetch: deskRefetch,
  } = useQuery({
    queryKey: ["endpoints", "list", { ...baseFilters, page }] as const,
    queryFn: async () => {
      const result = await listEndpoints({ ...baseFilters, page });
      if (result.max_page === 0 && page !== 1) {
        setPage(1);
      } else if (result.max_page > 0 && page > result.max_page) {
        setPage(result.max_page);
      }
      return result;
    },
    // Without this, reapplying a previously-fetched filter set returns the
    // cached result inside the default freshness window — looks broken.
    staleTime: 0,
    // Keep the prior page's rows on screen while a new filter set loads. This
    // avoids the loading state swapping out the table header mid-interaction —
    // which would otherwise close an open multi-select dropdown after each pick.
    placeholderData: keepPreviousData,
    enabled: isDesktop,
  });

  // Mobile: infinite scroll accumulating pages.
  const infiniteQuery = useInfiniteQuery({
    queryKey: ["endpoints", "infinite", baseFilters] as const,
    queryFn: ({ pageParam }) =>
      listEndpoints({ ...baseFilters, page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (last) =>
      last.page < last.max_page ? last.page + 1 : undefined,
    staleTime: 0,
    enabled: !isDesktop,
  });

  const listIsLoading = isDesktop ? deskLoading : infiniteQuery.isLoading;
  const listIsError = isDesktop ? deskError : infiniteQuery.isError;
  const items = isDesktop
    ? (data?.items ?? [])
    : (infiniteQuery.data?.pages.flatMap((p) => p.items) ?? []);
  const detail = useSheetDetail(items, (endpoint) => endpoint.id);
  const selectedEndpoints = [...selectedById.values()];
  const allShownSelected =
    items.length > 0 &&
    items.every((endpoint) => selectedById.has(endpoint.id));
  const someShownSelected = items.some((endpoint) =>
    selectedById.has(endpoint.id),
  );

  const toggleBulkSelection = (endpoint: Endpoint) => {
    setSelectedById((current) => {
      const next = new Map(current);
      if (next.has(endpoint.id)) {
        next.delete(endpoint.id);
      } else if (next.size < 50) {
        next.set(endpoint.id, endpoint);
      } else {
        toast.error(t("bulk.limit"));
      }
      return next;
    });
  };

  const toggleShownSelection = () => {
    if (allShownSelected) {
      setSelectedById(new Map());
      return;
    }
    setSelectedById((current) => {
      const next = new Map(current);
      let limitReached = false;
      for (const endpoint of items) {
        if (next.has(endpoint.id)) continue;
        if (next.size === 50) {
          limitReached = true;
          break;
        }
        next.set(endpoint.id, endpoint);
      }
      if (limitReached) toast.error(t("bulk.limit"));
      return next;
    });
  };

  const filterCount =
    chainFilter.length +
    networkFilter.length +
    (stateFilter !== "all" ? 1 : 0) +
    (providerId ? 1 : 0);
  const hasActiveFilter = filterCount > 0;

  const clearFilters = () => {
    table.resetPage();
    setSelectedById(new Map());
    setChainFilter([]);
    setNetworkFilter([]);
    setStateFilter("all");
    onClearProvider?.();
  };

  const toggleEnabled = (endpoint: Endpoint) => {
    if (updateMutation.isPending) return;
    setTogglingId(endpoint.id);
    updateMutation.mutate(
      {
        id: endpoint.id,
        input: {
          expected_version: endpoint.version,
          enabled: !endpoint.enabled,
        },
      },
      {
        onSuccess: (updated) =>
          toast.success(
            updated.enabled ? t("toast.enabled") : t("toast.disabled"),
          ),
        onError: (error) => {
          if (isDesktop) deskRefetch();
          else infiniteQuery.refetch();
          toast.error(
            isApiError(error) ? error.message : t("toast.updateError"),
          );
        },
        onSettled: () => setTogglingId(null),
      },
    );
  };

  const chainLabels = labelMap(CHAINS, (c) => t(`chain.${c}`));
  const networkLabels = labelMap(NETWORKS, (n) => t(`network.${n}`));
  const stateLabels: Record<StateFilter, string> = {
    all: t("filters.allStates"),
    true: t("state.enabled"),
    false: t("state.disabled"),
  };

  const columnLabels: Record<EndpointColumnKey, string> = {
    name: t("table.name"),
    chain: t("table.chain"),
    network: t("table.network"),
    protocol: t("table.protocol"),
    origin: t("table.provider"),
    state: t("table.state"),
  };

  const tableHeader = (
    <TableHeader>
      <TableRow>
        {!isProvider ? (
          <TableHead className="w-12">
            <Checkbox
              checked={
                allShownSelected
                  ? true
                  : someShownSelected
                    ? "indeterminate"
                    : false
              }
              onCheckedChange={toggleShownSelection}
              aria-label={
                allShownSelected
                  ? t("bulk.clearSelection")
                  : t("bulk.selectAll")
              }
            />
          </TableHead>
        ) : null}
        {table.isColumnVisible("name") ? (
          <TableHead>{t("table.name")}</TableHead>
        ) : null}
        {table.isColumnVisible("chain") ? (
          <TableHead>
            <MultiHeaderFilter
              label={t("table.chain")}
              allLabel={t("filters.allChains")}
              options={CHAINS}
              optionLabels={chainLabels}
              renderOption={(chain) => (
                <>
                  <span aria-hidden>
                    <ChainIcon chain={chain} className="size-4 shrink-0" />
                  </span>
                  {chainLabels[chain]}
                </>
              )}
              value={chainFilter}
              onValueChange={(next) => {
                table.resetPage();
                setSelectedById(new Map());
                setChainFilter(next);
              }}
            />
          </TableHead>
        ) : null}
        {table.isColumnVisible("network") ? (
          <TableHead>
            <MultiHeaderFilter
              label={t("table.network")}
              allLabel={t("filters.allNetworks")}
              options={NETWORKS}
              optionLabels={networkLabels}
              value={networkFilter}
              onValueChange={(next) => {
                table.resetPage();
                setSelectedById(new Map());
                setNetworkFilter(next);
              }}
            />
          </TableHead>
        ) : null}
        {table.isColumnVisible("protocol") ? (
          <TableHead>{t("table.protocol")}</TableHead>
        ) : null}
        {table.isColumnVisible("origin") ? (
          <TableHead>{t("table.provider")}</TableHead>
        ) : null}
        {table.isColumnVisible("state") ? (
          <TableHead>
            <HeaderFilter
              label={t("table.state")}
              options={STATE_OPTIONS}
              optionLabels={stateLabels}
              value={stateFilter}
              onValueChange={(next) => {
                table.resetPage();
                setSelectedById(new Map());
                setStateFilter(next);
              }}
            />
          </TableHead>
        ) : null}
        <TableHead align="right">
          <ColumnsToggle
            label={t("table.columnsLabel")}
            columns={columns}
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
        getKey={(e) => e.id}
        isLoading={listIsLoading}
        isError={listIsError}
        table={table}
        tableHeader={tableHeader}
        extraColSpan={isProvider ? 1 : 2}
        renderRow={(endpoint) => (
          <EndpointRow
            key={endpoint.id}
            endpoint={endpoint}
            visibleColumns={table.visibleColumns}
            selectable={!isProvider}
            bulkSelected={selectedById.has(endpoint.id)}
            selected={detail.isSelected(endpoint.id)}
            togglePending={togglingId === endpoint.id}
            onSelect={detail.toggle}
            onEdit={setEditTarget}
            onAudit={setAuditTarget}
            onToggleEnabled={toggleEnabled}
            onDelete={setDeleteTarget}
            onBulkSelect={toggleBulkSelection}
          />
        )}
        renderCard={(endpoint) => (
          <EndpointCard
            endpoint={endpoint}
            selectable={!isProvider}
            selected={selectedById.has(endpoint.id)}
            onSelect={toggleBulkSelection}
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
          <>
            {/* The provider scope arrives by deep link, not from this toolbar,
                so it needs a visible chip on every viewport — otherwise the
                table just looks short. */}
            {providerId ? (
              <Badge variant="brand" className="gap-1.5 py-1 pr-1 pl-2.5">
                {t("filters.providerFilter", {
                  name: providerQuery.data?.name ?? providerId,
                })}
                <button
                  type="button"
                  aria-label={t("filters.clearProviderFilter")}
                  onClick={() => {
                    table.resetPage();
                    setSelectedById(new Map());
                    onClearProvider?.();
                  }}
                  className="inline-flex size-4 items-center justify-center rounded-full text-current transition-colors hover:bg-brand/20"
                >
                  <XIcon className="size-3" aria-hidden />
                </button>
              </Badge>
            ) : null}
            {/* Desktop keeps its filters in the table headers; mobile bundles
                chain / network / state in a drawer. */}
            {isDesktop ? null : (
              <FilterDrawer
                label={t("filters.title")}
                title={t("filters.title")}
                activeCount={filterCount}
                onReset={clearFilters}
                resetLabel={t("filteredEmpty.cta")}
                doneLabel={t("filters.done")}
              >
                <FilterMultiGroup
                  label={t("table.chain")}
                  options={CHAINS}
                  optionLabels={chainLabels}
                  value={chainFilter}
                  onValueChange={(next) => {
                    table.resetPage();
                    setSelectedById(new Map());
                    setChainFilter(next);
                  }}
                />
                <FilterMultiGroup
                  label={t("table.network")}
                  options={NETWORKS}
                  optionLabels={networkLabels}
                  value={networkFilter}
                  onValueChange={(next) => {
                    table.resetPage();
                    setSelectedById(new Map());
                    setNetworkFilter(next);
                  }}
                />
                <FilterSingleGroup
                  label={t("table.state")}
                  options={STATE_OPTIONS}
                  optionLabels={stateLabels}
                  value={stateFilter}
                  onValueChange={(next) => {
                    table.resetPage();
                    setSelectedById(new Map());
                    setStateFilter(next);
                  }}
                />
              </FilterDrawer>
            )}
            {!isDesktop && !isProvider && items.length > 0 ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={toggleShownSelection}
              >
                {allShownSelected
                  ? t("bulk.clearSelection")
                  : t("bulk.selectAll")}
              </Button>
            ) : null}
          </>
        }
        pagination={{
          page: data?.page ?? page,
          maxPage: Math.max(1, data?.max_page ?? 1),
          pageSize: ENDPOINT_PAGE_SIZE,
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
          onRetry: () => (isDesktop ? deskRefetch() : infiniteQuery.refetch()),
          empty: isProvider
            ? {
                title: t("empty.providerTitle"),
                body: t("empty.providerBody"),
                cta: t("cta.manageProviders"),
                href: PROVIDERS_HREF,
              }
            : {
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

      {isDesktop ? (
        <EndpointDetailSheet
          endpoint={detail.selected}
          open={detail.open}
          onOpenChange={detail.onOpenChange}
          onEdit={setEditTarget}
          onAudit={setAuditTarget}
          onDelete={setDeleteTarget}
        />
      ) : null}
      <EditEndpointSheet
        endpoint={editTarget}
        open={editTarget !== null}
        onOpenChange={(open) => {
          if (!open) setEditTarget(null);
        }}
      />
      <DeleteEndpointDialog
        endpoint={deleteTarget}
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        onDeleted={(id) => {
          if (detail.selectedId === id) detail.close();
          setSelectedById((current) => {
            const next = new Map(current);
            next.delete(id);
            return next;
          });
        }}
      />
      <BulkDeleteEndpointsDialog
        endpoints={selectedEndpoints}
        open={bulkDeleteOpen}
        onOpenChange={onBulkDeleteOpenChange}
        onCompleted={(result) => {
          const deletedIds = new Set(result.deleted.map((item) => item.id));
          setSelectedById((current) => {
            const next = new Map(current);
            for (const endpointId of deletedIds) next.delete(endpointId);
            return next;
          });
          if (detail.selectedId && deletedIds.has(detail.selectedId)) {
            detail.close();
          }
        }}
      />
      <EndpointAuditDialog
        endpoint={auditTarget}
        open={auditTarget !== null}
        onOpenChange={(open) => {
          if (!open) setAuditTarget(null);
        }}
      />
    </>
  );
}

function labelMap<T extends string>(
  options: readonly T[],
  label: (option: T) => string,
): Record<T, string> {
  return Object.fromEntries(options.map((o) => [o, label(o)])) as Record<
    T,
    string
  >;
}
