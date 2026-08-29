"use client";

import { Search } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { isApiError } from "@/api/client";
import type {
  ListGatewaysParams,
  RpcGatewayBase,
  RpcGatewayTransport,
} from "@/api/gateways/client";
import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { MotionList } from "@/components/patterns/motion-list";
import { Button } from "@/components/ui/button";
import { ChainGroup } from "@/components/ui/chain-group";
import { ChainIcon } from "@/components/ui/chain-icon";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { HeaderFilter } from "@/components/ui/table-toolbar";
import {
  useBulkUpdateGatewaysMutation,
  useGatewaysQuery,
} from "@/hooks/use-gateways";
import { copyToClipboard } from "@/lib/clipboard";
import { chainLabel, RPC_CHAINS, type RpcChain } from "@/lib/rpc-chain";

import { groupNetworks } from "./app-networks";
import { GatewayNetworkRow } from "./gateway-network-row";
import type { useGatewayPathKey } from "./use-gateway-path-key";

type GatewayPathKeyState = ReturnType<typeof useGatewayPathKey>;

// The list API caps `size` at 50. An app owns at most one gateway per
// (chain, network) pair (~21 across the registry), so a single 50-item page
// always covers the full set.
const APP_GATEWAYS_SIZE = 50;

// Canonical order for the per-chain protocol selector. gRPC is omitted on
// purpose: rows only surface copy-and-go HTTP endpoints.
type DisplayTransport = Exclude<RpcGatewayTransport, "grpc">;

const DISPLAY_TRANSPORT_ORDER: readonly DisplayTransport[] = [
  "jsonrpc",
  "http_api",
];

// Toolbar controls that map onto real backend list params: status → `enabled`,
// sort → `created_at` direction, search → `search`. There is intentionally no
// network-type (mainnet/testnet) or name-sort control: the API has no such
// parameter, so those would only be a frontend illusion.
type StatusFilter = "all" | "enabled" | "disabled";
type SortOption = "created-desc" | "created-asc";

type GatewayListReturnState = {
  searchInput: string;
  chainFilter: RpcChain | "all";
  statusFilter: StatusFilter;
  sort: SortOption;
  chainOptions: RpcChain[];
  scrollTop: number;
};

const GATEWAY_LIST_RETURN_STATE_PREFIX = "gateway-list-return:";

/**
 * App detail body: the app's gateways grouped by chain as an Alchemy-style
 * "networks" view. Each gateway is a (chain, network) pair; rows surface the
 * selected endpoint and current status. The toolbar (search / status / sort)
 * drives the backend list query; grouping by chain is the only client-side
 * step.
 */
export function AppNetworksPanel({
  appId,
  pathKeyState,
}: {
  appId: string;
  pathKeyState: GatewayPathKeyState;
}) {
  const t = useTranslations("dashboard.apps");
  const tn = useTranslations("dashboard.apps.detail.networks");

  // Raw input vs. the debounced value actually sent to the server.
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  useEffect(() => {
    const id = setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => clearTimeout(id);
  }, [searchInput]);
  const [chainFilter, setChainFilter] = useState<RpcChain | "all">("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sort, setSort] = useState<SortOption>("created-desc");
  const [chainOptions, setChainOptions] = useState<RpcChain[]>([]);
  const [returnStateReady, setReturnStateReady] = useState(false);
  const [bulkPending, setBulkPending] = useState(false);
  const [confirmDisableAll, setConfirmDisableAll] = useState(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const pendingScrollTop = useRef<number | null>(null);

  // A detail navigation records a one-shot return state. Restore filters first
  // so the same rows are present, then restore the inner list viewport after
  // that filtered query has rendered.
  useEffect(() => {
    const saved = readGatewayListReturnState(appId);
    if (saved) {
      setSearchInput(saved.searchInput);
      setSearch(saved.searchInput.trim());
      setChainFilter(saved.chainFilter);
      setStatusFilter(saved.statusFilter);
      setSort(saved.sort);
      setChainOptions(saved.chainOptions);
      pendingScrollTop.current = saved.scrollTop;
    }
    setReturnStateReady(true);
  }, [appId]);

  const queryParams: ListGatewaysParams = {
    app_id: appId,
    size: APP_GATEWAYS_SIZE,
    search: search || undefined,
    chain: chainFilter === "all" ? undefined : chainFilter,
    enabled: statusFilter === "all" ? undefined : statusFilter === "enabled",
    sort: sort === "created-asc" ? "ASC" : "DESC",
  };

  const query = useGatewaysQuery(queryParams);
  const bulkUpdate = useBulkUpdateGatewaysMutation();

  const items = useMemo(() => query.data?.items ?? [], [query.data]);
  const groups = useMemo(() => groupNetworks(items), [items]);
  const { pathKey, status: pathKeyStatus } = pathKeyState;
  const pathKeyCopyDisabled = pathKeyStatus !== "available";
  const hasActiveFilter =
    search !== "" || chainFilter !== "all" || statusFilter !== "all";
  const enableTargets = items.filter((gw) => !gw.enabled);
  const disableTargets = items.filter((gw) => gw.enabled);

  // Chains this app spans, accumulated from the gateway list (the default,
  // unfiltered load surfaces them all) so the chain filter's options stay
  // stable while filtering. Drives the backend `chain` param; the filter only
  // appears once the app spans more than one chain.
  useEffect(() => {
    setChainOptions((prev) => {
      const seen = new Set<RpcChain>(prev);
      for (const gw of items) seen.add(gw.chain);
      return RPC_CHAINS.filter((c) => seen.has(c));
    });
  }, [items]);

  useEffect(() => {
    if (!returnStateReady || query.isLoading || query.isError) return;
    const scrollTop = pendingScrollTop.current;
    if (scrollTop === null) return;
    const frame = requestAnimationFrame(() => {
      if (scrollContainerRef.current) {
        scrollContainerRef.current.scrollTop = scrollTop;
      }
      pendingScrollTop.current = null;
    });
    return () => cancelAnimationFrame(frame);
  }, [returnStateReady, query.isLoading, query.isError]);

  const rememberReturnState = () => {
    writeGatewayListReturnState(appId, {
      searchInput,
      chainFilter,
      statusFilter,
      sort,
      chainOptions,
      scrollTop: scrollContainerRef.current?.scrollTop ?? 0,
    });
  };

  const handleCopy = async (url: string) => {
    const ok = await copyToClipboard(url);
    if (ok) toast.success(t("toast.copyOk"));
    else toast.error(t("toast.copyError"));
  };

  const toggleAll = async (enabled: boolean) => {
    const targets = items.filter((gw) => gw.enabled !== enabled);
    if (targets.length === 0) {
      if (!enabled) setConfirmDisableAll(false);
      return;
    }
    setBulkPending(true);
    try {
      await bulkUpdate.mutateAsync({
        appId,
        enabled,
        gateways: targets.map((gateway) => ({
          id: gateway.id,
          expected_version: gateway.version,
        })),
      });
      toast.success(enabled ? tn("bulkEnabled") : tn("bulkDisabled"));
      if (!enabled) setConfirmDisableAll(false);
    } catch (error) {
      await query.refetch();
      toast.error(
        isApiError(error) && error.message ? error.message : tn("bulkError"),
      );
    } finally {
      setBulkPending(false);
    }
  };

  const clearFilters = () => {
    setSearchInput("");
    setSearch("");
    setChainFilter("all");
    setStatusFilter("all");
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5">
      {/* Toolbar: one equal-height baseline. Each control maps to a backend list
       * param (search / enabled / created sort) and self-describes its value, so
       * there are no floating captions. Stays pinned above the scroll region. */}
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        <div className="relative w-full sm:w-60">
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-400"
            aria-hidden
          />
          <Input
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder={tn("searchPlaceholder")}
            aria-label={tn("searchAria")}
            className="h-9 py-0 pl-9 text-sm"
          />
        </div>

        {chainOptions.length > 1 ? (
          <Select
            value={chainFilter}
            onValueChange={(v) => setChainFilter(v as RpcChain | "all")}
          >
            <SelectTrigger
              aria-label={tn("chain")}
              className="h-9 w-36 py-0 text-sm"
            >
              {chainFilter === "all" ? (
                <>
                  <span aria-hidden>
                    <ChainGroup chains={chainOptions} max={5} />
                  </span>
                  <span className="sr-only">{tn("allChains")}</span>
                </>
              ) : (
                <span className="flex min-w-0 items-center gap-2">
                  <ChainIcon chain={chainFilter} className="size-4 shrink-0" />
                  <SelectValue />
                </span>
              )}
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">
                <span aria-hidden>
                  <ChainGroup chains={chainOptions} max={5} />
                </span>
                <span className="sr-only">{tn("allChains")}</span>
              </SelectItem>
              {chainOptions.map((chain) => (
                <SelectItem
                  key={chain}
                  value={chain}
                  icon={<ChainIcon chain={chain} className="size-4 shrink-0" />}
                >
                  {chainLabel(chain)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : null}

        <Select
          value={statusFilter}
          onValueChange={(v) => setStatusFilter(v as StatusFilter)}
        >
          <SelectTrigger
            aria-label={tn("status")}
            className="h-9 w-36 py-0 text-sm"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{tn("statusFilter.all")}</SelectItem>
            <SelectItem value="enabled">
              {tn("statusFilter.enabled")}
            </SelectItem>
            <SelectItem value="disabled">
              {tn("statusFilter.disabled")}
            </SelectItem>
          </SelectContent>
        </Select>

        <Select value={sort} onValueChange={(v) => setSort(v as SortOption)}>
          <SelectTrigger
            aria-label={tn("sortBy")}
            className="h-9 w-40 py-0 text-sm"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="created-desc">
              {tn("sort.createdDesc")}
            </SelectItem>
            <SelectItem value="created-asc">{tn("sort.createdAsc")}</SelectItem>
          </SelectContent>
        </Select>

        <div className="ml-auto flex items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-9"
            disabled={bulkPending || disableTargets.length === 0}
            onClick={() => setConfirmDisableAll(true)}
          >
            {tn("disableAll")}
          </Button>
          <Button
            type="button"
            variant="pill-primary"
            size="sm"
            className="h-9"
            disabled={bulkPending || enableTargets.length === 0}
            onClick={() => toggleAll(true)}
          >
            {tn("enableAll")}
          </Button>
        </div>
      </div>

      {/* Only this region scrolls; the toolbar above stays pinned. On mobile the
       * column isn't height-bounded, so it simply flows with the page.
       * `overflow-y-auto` makes overflow-x compute to `auto` too, which would
       * clip each card's soft shadow at the edges; the inner padding (offset by
       * a matching negative margin so cards stay aligned) gives the shadow room. */}
      <div
        ref={scrollContainerRef}
        data-slot="gateway-list-scroll"
        className="no-scrollbar -mx-2 flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-2 pt-1 pb-2"
      >
        {/* Body states. */}
        {query.isLoading ? <NetworksSkeleton /> : null}

        {!query.isLoading && query.isError ? (
          <div
            role="alert"
            className="mx-auto flex max-w-prose-narrow flex-col items-center gap-2 py-14 text-center"
          >
            <p className="text-lg font-semibold text-ink-900">
              {t("error.title")}
            </p>
            <p className="text-md text-ink-500">{t("error.body")}</p>
            <button
              type="button"
              onClick={() => query.refetch()}
              className="mt-2 inline-flex h-9 items-center rounded-md bg-brand-soft px-4 text-sm font-semibold text-brand transition-colors hover:bg-brand hover:text-white"
            >
              {t("error.retry")}
            </button>
          </div>
        ) : null}

        {!query.isLoading &&
        !query.isError &&
        items.length === 0 &&
        !hasActiveFilter ? (
          <div className="mx-auto flex max-w-prose-narrow flex-col items-center gap-2 py-14 text-center">
            <p className="text-lg font-semibold text-ink-900">
              {t("detail.gatewaysTitle")}
            </p>
            <p className="text-md text-ink-500">{t("detail.emptyGateways")}</p>
          </div>
        ) : null}

        {!query.isLoading &&
        !query.isError &&
        items.length === 0 &&
        hasActiveFilter ? (
          <div className="mx-auto flex max-w-prose-narrow flex-col items-center gap-2 py-14 text-center">
            <p className="text-md text-ink-500">{tn("filteredEmpty")}</p>
            <button
              type="button"
              onClick={clearFilters}
              className="text-sm font-semibold text-brand transition-colors hover:text-brand-hover"
            >
              {tn("clearFilters")}
            </button>
          </div>
        ) : null}

        {!query.isLoading && !query.isError && groups.length > 0 ? (
          <div className="flex flex-col gap-5">
            {groups.map((group) => (
              <ChainCard
                key={group.chain}
                appId={appId}
                chain={group.chain}
                gateways={group.gateways}
                onCopy={handleCopy}
                onNavigate={rememberReturnState}
                pathKey={pathKey}
                pathKeyCopyDisabled={pathKeyCopyDisabled}
              />
            ))}
          </div>
        ) : null}
      </div>

      <ConfirmDialog
        open={confirmDisableAll}
        onOpenChange={setConfirmDisableAll}
        title={tn("disableDialog.title")}
        description={tn("disableDialog.body", {
          count: disableTargets.length,
        })}
        onConfirm={() => toggleAll(false)}
        confirmLabel={tn("disableDialog.confirm")}
        confirmingLabel={tn("disableDialog.confirming")}
        cancelLabel={tn("disableDialog.cancel")}
        confirming={bulkPending}
        destructive
      />
    </div>
  );
}

function ChainCard({
  appId,
  chain,
  gateways,
  onCopy,
  onNavigate,
  pathKey,
  pathKeyCopyDisabled,
}: {
  appId: string;
  chain: RpcGatewayBase["chain"];
  gateways: RpcGatewayBase[];
  onCopy: (url: string) => void;
  onNavigate: () => void;
  pathKey: string | null;
  pathKeyCopyDisabled: boolean;
}) {
  const tn = useTranslations("dashboard.apps.detail.networks");

  // Protocols this chain group actually exposes, in a canonical display order.
  // gRPC is intentionally excluded — it isn't a copy-and-go HTTP endpoint. The
  // endpoint-column picker only appears when a group offers more than one.
  const transportOptions = useMemo(() => {
    const seen = new Set<RpcGatewayTransport>();
    for (const gw of gateways)
      for (const ap of gw.access_points) seen.add(ap.transport);
    return DISPLAY_TRANSPORT_ORDER.filter((tr) => seen.has(tr));
  }, [gateways]);

  const [transport, setTransport] = useState<DisplayTransport>(
    transportOptions[0] ?? "jsonrpc",
  );
  // Keep the selection valid if the available protocols shift under us.
  useEffect(() => {
    if (!transportOptions.includes(transport))
      setTransport(transportOptions[0] ?? "jsonrpc");
  }, [transportOptions, transport]);

  const transportLabels: Record<DisplayTransport, string> = {
    jsonrpc: tn("transport.jsonrpc"),
    http_api: tn("transport.http_api"),
  };

  return (
    <section className="overflow-hidden rounded-2xl bg-surface shadow-section">
      {/* The card header identifies the chain only. Protocol selection belongs
       * to the endpoint column it controls, alongside the other column labels. */}
      <header className="flex items-center gap-2.5 px-5 py-4">
        <ChainIcon chain={chain} className="size-6" />
        <h2 className="text-lg font-semibold text-ink-900">
          {chainLabel(chain)}
        </h2>
      </header>

      {/* On narrow screens only the protocol control remains visible; desktop
       * aligns it with the endpoint column and restores the other labels. */}
      <div className="grid grid-cols-1 items-center px-5 pb-2 text-2xs font-medium uppercase tracking-wide text-ink-400 md:grid-cols-12 md:gap-3">
        <span className="hidden md:col-span-2 md:block">
          {tn("col.network")}
        </span>
        <div className="md:col-span-8">
          {transportOptions.length > 1 ? (
            <HeaderFilter
              label={transportLabels.jsonrpc}
              value={transport}
              onValueChange={setTransport}
              options={transportOptions}
              optionLabels={transportLabels}
              allValue="jsonrpc"
            />
          ) : (
            transportLabels[transport]
          )}
        </div>
        <span className="hidden md:col-span-1 md:block">
          {tn("col.status")}
        </span>
        <span className="hidden md:col-span-1 md:block" />
      </div>

      {/* `as="ul"` keeps the list semantic: a div between <ul> and <li> would
          be invalid HTML and would break the divide-y hairlines. */}
      <MotionList as="ul" className="flex flex-col divide-y divide-ink-wash">
        {gateways.map((gw) => (
          <GatewayNetworkRow
            key={gw.id}
            appId={appId}
            gateway={gw}
            transport={transport}
            onCopy={onCopy}
            onNavigate={onNavigate}
            pathKey={pathKey}
            pathKeyCopyDisabled={pathKeyCopyDisabled}
          />
        ))}
      </MotionList>
    </section>
  );
}

function returnStateKey(appId: string): string {
  return `${GATEWAY_LIST_RETURN_STATE_PREFIX}${appId}`;
}

function readGatewayListReturnState(
  appId: string,
): GatewayListReturnState | null {
  try {
    const raw = sessionStorage.getItem(returnStateKey(appId));
    if (!raw) return null;
    sessionStorage.removeItem(returnStateKey(appId));
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== "object") return null;
    const saved = value as Partial<GatewayListReturnState>;
    const chainFilter = isRpcChain(saved.chainFilter)
      ? saved.chainFilter
      : saved.chainFilter === "all"
        ? "all"
        : null;
    if (
      typeof saved.searchInput !== "string" ||
      chainFilter === null ||
      !isStatusFilter(saved.statusFilter) ||
      !isSortOption(saved.sort) ||
      !Array.isArray(saved.chainOptions) ||
      !saved.chainOptions.every(isRpcChain) ||
      typeof saved.scrollTop !== "number" ||
      !Number.isFinite(saved.scrollTop) ||
      saved.scrollTop < 0
    ) {
      return null;
    }
    return {
      searchInput: saved.searchInput,
      chainFilter,
      statusFilter: saved.statusFilter,
      sort: saved.sort,
      chainOptions: saved.chainOptions,
      scrollTop: saved.scrollTop,
    };
  } catch {
    return null;
  }
}

function writeGatewayListReturnState(
  appId: string,
  state: GatewayListReturnState,
): void {
  try {
    sessionStorage.setItem(returnStateKey(appId), JSON.stringify(state));
  } catch {
    // Storage can be unavailable in privacy-restricted browser contexts.
  }
}

function isRpcChain(value: unknown): value is RpcChain {
  return (
    typeof value === "string" &&
    (RPC_CHAINS as readonly string[]).includes(value)
  );
}

function isStatusFilter(value: unknown): value is StatusFilter {
  return value === "all" || value === "enabled" || value === "disabled";
}

function isSortOption(value: unknown): value is SortOption {
  return value === "created-desc" || value === "created-asc";
}

function NetworksSkeleton() {
  return (
    <div className="flex flex-col gap-5">
      {[0, 1].map((i) => (
        <section
          key={i}
          className="overflow-hidden rounded-2xl bg-surface shadow-section"
        >
          <div className="flex items-center gap-2.5 px-5 py-4">
            <Skeleton className="size-6 rounded-full" />
            <Skeleton className="h-5 w-28" />
          </div>
          <div className="flex flex-col divide-y divide-ink-wash">
            {[0, 1].map((row) => (
              <div key={row} className="flex items-center gap-3 px-5 py-4">
                <Skeleton className="h-5 w-40" />
                <Skeleton className="h-4 flex-1" />
                <Skeleton className="h-7 w-20 rounded-full" />
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
