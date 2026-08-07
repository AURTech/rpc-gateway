"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import {
  type ListProvidersParams,
  listProviders,
  RPC_PROVIDER_VENDORS,
  type RpcProviderVendor,
} from "@/api/providers/client";
import { CardGridView } from "@/components/patterns/card-grid-view";
import { ToolbarFilter } from "@/components/ui/table-toolbar";
import { Toolbar, ToolbarGroup } from "@/components/ui/toolbar";
import { providersKeys } from "@/hooks/use-providers";

import { ProviderCard } from "./provider-card";
import { ProviderCardSkeleton } from "./provider-card-skeleton";
import { ProviderDetailSheet } from "./provider-detail-sheet";
import { replaceProviderSearchParam } from "./provider-url-state";
import { VendorFilterChips } from "./vendor-filter-chips";

type EnabledFilter = "all" | "enabled" | "disabled";
type SyncFilter = "all" | "on" | "off";
const PROVIDER_PAGE_SIZE = 12;

/** Shared filter params (no `page`) for the infinite query. */
function buildBaseFilters(
  vendorFilter: readonly RpcProviderVendor[],
  enabledFilter: EnabledFilter,
  syncFilter: SyncFilter,
): Omit<ListProvidersParams, "page"> {
  const f: Omit<ListProvidersParams, "page"> = {
    size: PROVIDER_PAGE_SIZE,
  };
  if (vendorFilter.length > 0) f.vendor = [...vendorFilter];
  if (enabledFilter === "enabled") f.enabled = true;
  if (enabledFilter === "disabled") f.enabled = false;
  if (syncFilter === "on") f.sync_enabled = true;
  if (syncFilter === "off") f.sync_enabled = false;
  return f;
}

/**
 * Account-owned providers view, backed by `/v2/providers`. Lists the
 * authenticated account's RPC vendor connections as a responsive card grid with
 * full create/edit/delete plus manual sync; users and admins share this surface
 * (the backend scopes the provider routes to the caller's account for either
 * identity). One infinite (load-more) query drives every viewport; the toolbar
 * is a brand chip row (vendor multi-select) that wraps on narrow screens, with
 * sunken dropdowns for auto-sync/state on the right.
 *
 * Tapping a card opens {@link ProviderDetailSheet} beside the grid rather than
 * navigating to a detail page. The open provider is mirrored into `?provider=`
 * so the drawer survives a reload and can be deep-linked into (the Endpoints
 * table's vendor chip links here).
 */
export function ProvidersContent({
  initialProviderId = null,
}: {
  /** Provider to open on mount, from the `?provider=` deep link. */
  initialProviderId?: string | null;
}) {
  const t = useTranslations("dashboard.providers");

  const [activeId, setActiveId] = useState<string | null>(initialProviderId);

  const [vendorFilter, setVendorFilter] = useState<
    readonly RpcProviderVendor[]
  >(() => []);
  const [enabledFilter, setEnabledFilter] = useState<EnabledFilter>("all");
  const [syncFilter, setSyncFilter] = useState<SyncFilter>("all");

  const baseFilters = useMemo(
    () => buildBaseFilters(vendorFilter, enabledFilter, syncFilter),
    [vendorFilter, enabledFilter, syncFilter],
  );

  const query = useInfiniteQuery({
    queryKey: providersKeys.infiniteList(baseFilters),
    queryFn: ({ pageParam }) =>
      listProviders({ ...baseFilters, page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (last) =>
      last.page < last.max_page ? last.page + 1 : undefined,
    // Without this, reapplying a previously-fetched filter set returns the
    // cached result inside the default freshness window — looks broken because
    // no new request fires even though the user changed a filter.
    staleTime: 0,
  });

  const items = useMemo(
    () => query.data?.pages.flatMap((p) => p.items) ?? [],
    [query.data],
  );

  const hasActiveFilter =
    vendorFilter.length > 0 || enabledFilter !== "all" || syncFilter !== "all";

  const clearFilters = () => {
    setVendorFilter([]);
    setEnabledFilter("all");
    setSyncFilter("all");
  };

  // The drawer's open provider is URL state so a reload (or a link from the
  // Endpoints table) reopens the same one.
  const openDetail = (id: string) => {
    setActiveId(id);
    replaceProviderSearchParam(id);
  };

  const closeDetail = () => {
    setActiveId(null);
    replaceProviderSearchParam(null);
  };

  const vendorLabels = Object.fromEntries(
    RPC_PROVIDER_VENDORS.map((v) => [v, t(`vendor.${v}`)] as const),
  ) as Record<RpcProviderVendor, string>;

  const stateOptions: EnabledFilter[] = ["all", "enabled", "disabled"];
  const stateLabels: Record<EnabledFilter, string> = {
    all: t("filters.stateAll"),
    enabled: t("filters.stateEnabled"),
    disabled: t("filters.stateDisabled"),
  };

  const syncOptions: SyncFilter[] = ["all", "on", "off"];
  const syncLabels: Record<SyncFilter, string> = {
    all: t("filters.syncAll"),
    on: t("filters.syncOn"),
    off: t("filters.syncOff"),
  };

  return (
    <div className="flex flex-col gap-4">
      <Toolbar>
        <ToolbarGroup>
          <VendorFilterChips
            options={RPC_PROVIDER_VENDORS}
            optionLabels={vendorLabels}
            allLabel={t("filters.allVendors")}
            value={vendorFilter}
            onValueChange={setVendorFilter}
          />
        </ToolbarGroup>
        <ToolbarGroup align="end">
          <ToolbarFilter
            label={t("table.autoSync")}
            options={syncOptions}
            optionLabels={syncLabels}
            value={syncFilter}
            onValueChange={setSyncFilter}
            triggerClassName={CHIP_TRIGGER_CLASS}
          />
          <ToolbarFilter
            label={t("table.state")}
            options={stateOptions}
            optionLabels={stateLabels}
            value={enabledFilter}
            onValueChange={setEnabledFilter}
            triggerClassName={CHIP_TRIGGER_CLASS}
          />
          {hasActiveFilter ? (
            <button
              type="button"
              onClick={clearFilters}
              className="inline-flex h-9 items-center rounded-full px-3 text-sm font-medium text-ink-500 transition-colors hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
            >
              {t("filteredEmpty.cta")}
            </button>
          ) : null}
        </ToolbarGroup>
      </Toolbar>

      <CardGridView
        items={items}
        getKey={(p) => p.id}
        gridClassName="lg:grid-cols-3 2xl:grid-cols-4"
        isLoading={query.isLoading}
        isError={query.isError}
        renderCard={(provider) => (
          <ProviderCard provider={provider} onOpen={openDetail} />
        )}
        renderSkeleton={() => <ProviderCardSkeleton />}
        infinite={{
          hasMore: query.hasNextPage,
          isFetchingMore: query.isFetchingNextPage,
          onLoadMore: () => {
            query.fetchNextPage();
          },
        }}
        states={{
          hasActiveFilter,
          onClearFilter: clearFilters,
          onRetry: () => query.refetch(),
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

      <ProviderDetailSheet
        providerId={activeId}
        open={activeId !== null}
        onOpenChange={(next) => {
          if (!next) closeDetail();
        }}
      />
    </div>
  );
}
// Sunken chip restyle for the single-select dropdowns so they sit on the same
// visual plane as the vendor chips (ink-wash fill, no card shadow).
const CHIP_TRIGGER_CLASS =
  "h-9 rounded-full bg-ink-wash px-3.5 shadow-none hover:bg-stripe";
