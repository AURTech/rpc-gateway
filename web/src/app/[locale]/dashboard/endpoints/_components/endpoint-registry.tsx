"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckSquare2,
  ChevronRight,
  HeartPulse,
  LoaderCircle,
  Pencil,
  Trash2,
} from "lucide-react";
import { AnimatePresence, motion, useIsPresent } from "motion/react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import type {
  Endpoint,
  EndpointOriginType,
  EndpointProtocol,
  ListEndpointsParams,
} from "@/api/endpoints/client";
import { listProviders } from "@/api/providers/client";
import {
  ALL_CHAIN_NETWORK_PAIRS,
  ChainNetworkOptionContent,
  chainNetworkValue,
} from "@/components/patterns/chain-network-select";
import { Button } from "@/components/ui/button";
import { ChainIcon } from "@/components/ui/chain-icon";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableExpandedRow,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  TableColumnFilter,
  TableColumnFilterPanel,
} from "@/components/ui/table-column-filter";
import { TablePagination } from "@/components/ui/table-pagination";
import { TableColumnsHead } from "@/components/ui/table-toolbar";
import {
  endpointDetailQueryOptions,
  useBulkDeleteEndpointsMutation,
  useCheckEndpointHealthMutation,
  useEndpointsQuery,
  useUpdateEndpointMutation,
} from "@/hooks/use-endpoints";
import { useInitialTableRowEntrance } from "@/hooks/use-initial-table-row-entrance";
import { useMotionPreset } from "@/hooks/use-motion-preset";
import { useTableController } from "@/hooks/use-table-controller";
import { usePathname, useRouter } from "@/i18n/navigation";
import type { Chain, Network } from "@/lib/blockchain";
import {
  emptyDetailVariants,
  transitionEnter,
  transitionExit,
} from "@/lib/motion";
import { cn } from "@/lib/utils";
import { ConnectProviderButton } from "../providers/_components/connect-provider-button";
import { CopyableEndpointUrl } from "./copyable-endpoint-url";
import { DeleteEndpointDialog } from "./delete-endpoint-dialog";
import { EndpointHealthStatus } from "./endpoint-health-status";
import { EndpointRowExpansion } from "./endpoint-row-expansion";
import { NewEndpointButton } from "./new-endpoint-button";

const PAGE_SIZE = 12;
const SKELETON_ROWS = Array.from({ length: PAGE_SIZE }, (_, index) => index);
const NETWORK_OPTIONS = ALL_CHAIN_NETWORK_PAIRS.map((pair) => ({
  value: chainNetworkValue(pair),
  ...pair,
}));
const PROTOCOL_OPTIONS = ["all", "jsonrpc", "http_api"] as const;
const ENDPOINT_OPTIONAL_COLUMNS = ["url", "network", "health"] as const;
type EndpointColumnKey = (typeof ENDPOINT_OPTIONAL_COLUMNS)[number];
type RegistryView = "all" | "manual" | "managed";
type ProtocolFilter = "all" | EndpointProtocol;

function parsePage(value: string | null): number {
  const page = Number(value);
  return Number.isInteger(page) && page > 0 ? page : 1;
}

function EndpointRegistry() {
  const t = useTranslations("dashboard.endpoints");
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [selection, setSelection] = useState<Set<string>>(new Set());
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deletingEndpoint, setDeletingEndpoint] = useState<Endpoint | null>(
    null,
  );
  const urlExpandedId = searchParams.get("expanded");
  const [expandedId, setExpandedId] = useState<string | null>(urlExpandedId);
  const columns = useTableController<EndpointColumnKey>({
    allColumns: ENDPOINT_OPTIONAL_COLUMNS,
  });

  const view = (searchParams.get("view") ?? "all") as RegistryView;
  const query = searchParams.get("q") ?? "";
  const chain = (searchParams.get("chain") ?? "all") as "all" | Chain;
  const network = (searchParams.get("network") ?? "all") as "all" | Network;
  const protocol = (searchParams.get("protocol") ?? "all") as ProtocolFilter;
  const providerId = searchParams.get("provider") ?? "";
  const page = parsePage(searchParams.get("page"));

  useEffect(() => {
    setExpandedId(urlExpandedId);
    setEditingId((current) => (current === urlExpandedId ? current : null));
  }, [urlExpandedId]);

  const originType: EndpointOriginType | undefined = providerId
    ? "provider"
    : view === "manual"
      ? "manual"
      : view === "managed"
        ? "provider"
        : undefined;
  const listParams = {
    origin_type: originType,
    chain: chain === "all" ? undefined : [chain],
    network: network === "all" ? undefined : [network],
    protocol: protocol === "all" ? undefined : protocol,
    provider_id: providerId || undefined,
    page,
    size: PAGE_SIZE,
    q: query || undefined,
  } satisfies ListEndpointsParams;
  const endpoints = useEndpointsQuery(listParams);
  const animateInitialRows = useInitialTableRowEntrance(
    !endpoints.isLoading && !endpoints.isError,
  );
  const providerContext = useQuery({
    queryKey: ["providers", "registry-context", providerId],
    queryFn: () => listProviders({ q: providerId, page: 1, size: 1 }),
    enabled: Boolean(providerId),
    staleTime: 15_000,
  });
  const bulkDelete = useBulkDeleteEndpointsMutation();

  function replaceSearchParams(next: URLSearchParams) {
    const query = next.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, {
      scroll: false,
    });
  }

  function setParam(key: string, value?: string) {
    const next = new URLSearchParams(searchParams.toString());
    if (value && value !== "all") next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    next.delete("expanded");
    setExpandedId(null);
    setEditingId(null);
    replaceSearchParams(next);
    setSelection(new Set());
  }

  function setNetworkPair(value: string) {
    const next = new URLSearchParams(searchParams.toString());
    const option = NETWORK_OPTIONS.find((item) => item.value === value);
    if (option) {
      next.set("chain", option.chain);
      next.set("network", option.network);
    } else {
      next.delete("chain");
      next.delete("network");
    }
    next.delete("page");
    next.delete("expanded");
    setExpandedId(null);
    setEditingId(null);
    replaceSearchParams(next);
    setSelection(new Set());
  }

  function setEndpointView(value: RegistryView) {
    const next = new URLSearchParams(searchParams.toString());
    if (value === "all") next.delete("view");
    else next.set("view", value);
    if (value !== "managed") next.delete("provider");
    next.delete("page");
    next.delete("expanded");
    setExpandedId(null);
    setEditingId(null);
    replaceSearchParams(next);
    setSelection(new Set());
  }

  function setExpanded(id: string | null) {
    setExpandedId(id);
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("expanded", id);
    else url.searchParams.delete("expanded");
    window.history.replaceState(window.history.state, "", url);
  }

  const manualItems = useMemo(
    () =>
      endpoints.data?.items.filter((item) => item.origin_type === "manual") ??
      [],
    [endpoints.data?.items],
  );
  const allManualSelected =
    manualItems.length > 0 &&
    manualItems.every((item) => selection.has(item.id));

  function toggleSelection(id: string, checked: boolean) {
    setSelection((current) => {
      const next = new Set(current);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  async function removeSelected() {
    try {
      await bulkDelete.mutateAsync([...selection]);
      toast.success(t("bulk.toast.deleted", { count: selection.size }));
      if (expandedId && selection.has(expandedId)) {
        setEditingId(null);
        setExpanded(null);
      }
      setSelection(new Set());
      setConfirmOpen(false);
    } catch {
      toast.error(t("bulk.toast.deleteError"));
    }
  }

  const hasFilters = Boolean(
    query ||
      chain !== "all" ||
      network !== "all" ||
      protocol !== "all" ||
      providerId,
  );

  const selectedNetworkOption = NETWORK_OPTIONS.find(
    (item) => item.chain === chain && item.network === network,
  );
  const selectedNetwork = selectedNetworkOption?.value ?? "all";
  const visibleProviderName = endpoints.data?.items.find(
    (endpoint) => endpoint.provider?.id === providerId,
  )?.provider?.name;
  const providerName =
    providerContext.data?.items.find((provider) => provider.id === providerId)
      ?.name ?? visibleProviderName;
  const endpointSummary = providerId
    ? (providerName ?? t("fields.provider"))
    : view === "all"
      ? null
      : t(`registry.views.${view}`);
  const endpointColumnLabel = endpointSummary
    ? `${t("registry.columns.endpoint")} · ${endpointSummary}`
    : t("registry.columns.endpoint");
  const networkSummary = selectedNetworkOption
    ? `${t(`chain.${selectedNetworkOption.chain}`)} ${t(`network.${selectedNetworkOption.network}`)}`
    : null;
  const protocolSummary = protocol === "all" ? null : t(`protocol.${protocol}`);
  const networkColumnSummary = [networkSummary, protocolSummary]
    .filter(Boolean)
    .join(" + ");
  const networkColumnLabel = networkColumnSummary
    ? `${t("registry.columns.network")} · ${networkColumnSummary}`
    : t("registry.columns.network");
  const columnLabels: Record<EndpointColumnKey, string> = {
    url: t("registry.columns.url"),
    network: t("registry.columns.network"),
    health: t("registry.columns.health"),
  };
  const columnCount =
    columns.visibleColumns.size + 2 + (view === "manual" ? 1 : 0);

  return (
    <div className="min-w-0">
      <section
        aria-label={t("registry.inventoryLabel")}
        className="flex min-w-0 flex-col gap-3"
      >
        {view === "manual" && selection.size > 0 ? (
          <div
            role="toolbar"
            aria-label={t("bulk.selectionActions")}
            className="flex min-h-12 items-center justify-between gap-4 rounded-xl bg-brand-soft px-4 py-2"
          >
            <span
              aria-live="polite"
              className="flex min-w-0 items-center gap-2 text-sm font-semibold text-ink-900"
            >
              <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-surface text-brand shadow-card">
                <CheckSquare2 className="size-4" aria-hidden />
              </span>
              {t("registry.selected", { count: selection.size })}
            </span>
            <div className="flex shrink-0 items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSelection(new Set())}
              >
                {t("bulk.clearSelection")}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-danger hover:bg-danger-soft hover:text-danger"
                onClick={() => setConfirmOpen(true)}
              >
                <Trash2 aria-hidden />
                {t("bulk.deleteSelectedCount", { count: selection.size })}
              </Button>
            </div>
          </div>
        ) : null}

        <Table
          rowSpotlight
          className="table-fixed"
          containerClassName="shadow-section"
          scrollClassName="h-table-viewport-12"
          footer={
            endpoints.data && endpoints.data.total > 0 ? (
              <div className="bg-table-frame px-4 py-3">
                <TablePagination
                  page={endpoints.data.page}
                  maxPage={Math.max(1, endpoints.data.max_page)}
                  pageSize={PAGE_SIZE}
                  pageItemCount={endpoints.data.items.length}
                  total={endpoints.data.total}
                  onPageChange={(next) => setParam("page", String(next))}
                  rangeLabel={(args) => t("table.range", args)}
                  prevLabel={t("table.prev")}
                  nextLabel={t("table.next")}
                />
              </div>
            ) : undefined
          }
        >
          <colgroup>
            {view === "manual" ? <col className="w-12" /> : null}
            <col className="w-56" />
            {columns.isColumnVisible("url") ? <col /> : null}
            {columns.isColumnVisible("network") ? (
              <col className="w-48" />
            ) : null}
            {columns.isColumnVisible("health") ? (
              <col className="w-28" />
            ) : null}
            <col className="w-44" />
          </colgroup>
          <TableHeader>
            <TableRow>
              {view === "manual" ? (
                <TableHead className="w-12">
                  <Checkbox
                    aria-label={t("bulk.selectAll")}
                    checked={allManualSelected}
                    onCheckedChange={(checked) =>
                      setSelection(
                        checked
                          ? new Set(manualItems.map((item) => item.id))
                          : new Set(),
                      )
                    }
                  />
                </TableHead>
              ) : null}
              <TableHead>
                <TableColumnFilter
                  label={endpointColumnLabel}
                  active={view !== "all" || Boolean(providerId)}
                >
                  <DropdownMenuRadioGroup
                    value={providerId ? "managed" : view}
                    onValueChange={(value) =>
                      setEndpointView(value as RegistryView)
                    }
                  >
                    {(["all", "manual", "managed"] as const).map((value) => (
                      <DropdownMenuRadioItem key={value} value={value}>
                        {t(`registry.views.${value}`)}
                      </DropdownMenuRadioItem>
                    ))}
                  </DropdownMenuRadioGroup>
                  {providerId ? (
                    <>
                      <DropdownMenuSeparator />
                      <DropdownMenuLabel className="max-w-56 truncate text-xs text-ink-400">
                        {t("filters.providerFilter", {
                          name: providerName ?? t("fields.provider"),
                        })}
                      </DropdownMenuLabel>
                      <DropdownMenuItem
                        onSelect={() => setParam("provider")}
                        className="text-ink-700"
                      >
                        {t("filters.clearProviderFilter")}
                      </DropdownMenuItem>
                    </>
                  ) : null}
                </TableColumnFilter>
              </TableHead>
              {columns.isColumnVisible("url") ? (
                <TableHead>{t("registry.columns.url")}</TableHead>
              ) : null}
              {columns.isColumnVisible("network") ? (
                <TableHead>
                  <TableColumnFilterPanel
                    label={networkColumnLabel}
                    active={
                      chain !== "all" || network !== "all" || protocol !== "all"
                    }
                    contentClassName="w-72 p-3"
                  >
                    <fieldset className="min-w-0">
                      <legend className="text-xs font-semibold text-ink-500">
                        {t("fields.protocol")}
                      </legend>
                      <div className="mt-2 grid grid-cols-3 gap-1">
                        {PROTOCOL_OPTIONS.map((value) => {
                          const selected = protocol === value;
                          return (
                            <button
                              key={value}
                              type="button"
                              aria-pressed={selected}
                              onClick={() => setParam("protocol", value)}
                              className={cn(
                                "rounded-md px-2 py-2 text-xs font-medium outline-none transition-colors hover:bg-ink-wash hover:text-ink-900 focus-visible:ring-2 focus-visible:ring-brand/30",
                                selected
                                  ? "bg-ink-wash text-ink-900"
                                  : "text-ink-500",
                              )}
                            >
                              {value === "all"
                                ? t("filters.all")
                                : t(`protocol.${value}`)}
                            </button>
                          );
                        })}
                      </div>
                    </fieldset>

                    <div className="my-3 h-px bg-table-frame" aria-hidden />

                    <fieldset className="min-w-0">
                      <legend className="text-xs font-semibold text-ink-500">
                        {t("fields.network")}
                      </legend>
                      <div className="mt-2 max-h-72 overflow-y-auto pr-1">
                        <button
                          type="button"
                          aria-pressed={selectedNetwork === "all"}
                          onClick={() => setNetworkPair("all")}
                          className={cn(
                            "flex w-full rounded-md px-2 py-2 text-left text-sm font-medium outline-none transition-colors hover:bg-ink-wash hover:text-ink-900 focus-visible:ring-2 focus-visible:ring-brand/30",
                            selectedNetwork === "all"
                              ? "bg-ink-wash text-ink-900"
                              : "text-ink-500",
                          )}
                        >
                          {t("filters.allNetworks")}
                        </button>
                        {ALL_CHAIN_NETWORK_PAIRS.map((pair) => {
                          const value = chainNetworkValue(pair);
                          const selected = selectedNetwork === value;
                          return (
                            <button
                              key={value}
                              type="button"
                              aria-pressed={selected}
                              onClick={() => setNetworkPair(value)}
                              className={cn(
                                "mt-0.5 flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm outline-none transition-colors hover:bg-ink-wash hover:text-ink-900 focus-visible:ring-2 focus-visible:ring-brand/30",
                                selected
                                  ? "bg-ink-wash font-medium text-ink-900"
                                  : "text-ink-500",
                              )}
                            >
                              <ChainNetworkOptionContent pair={pair} />
                            </button>
                          );
                        })}
                      </div>
                    </fieldset>
                  </TableColumnFilterPanel>
                </TableHead>
              ) : null}
              {columns.isColumnVisible("health") ? (
                <TableHead>{t("registry.columns.health")}</TableHead>
              ) : null}
              <TableColumnsHead
                label={t("registry.columnsLabel")}
                columns={ENDPOINT_OPTIONAL_COLUMNS}
                labels={columnLabels}
                value={columns.visibleColumns}
                onValueChange={columns.setVisibleColumns}
              />
            </TableRow>
          </TableHeader>
          <TableBody refreshing={endpoints.isPlaceholderData}>
            {endpoints.isLoading ? (
              <RegistryLoading colSpan={columnCount} />
            ) : null}
            {endpoints.isError ? (
              <RegistryMessage
                colSpan={columnCount}
                title={t("error.title")}
                body={t("error.body")}
                action={
                  <Button
                    size="sm"
                    variant="soft"
                    onClick={() => endpoints.refetch()}
                  >
                    {t("error.retry")}
                  </Button>
                }
              />
            ) : null}
            {endpoints.data?.items.map((endpoint, index) => (
              <EndpointLedgerRow
                key={endpoint.id}
                endpoint={endpoint}
                showSelection={view === "manual"}
                selected={selection.has(endpoint.id)}
                onSelectedChange={(checked) =>
                  toggleSelection(endpoint.id, checked)
                }
                expanded={expandedId === endpoint.id}
                editing={editingId === endpoint.id}
                colSpan={columnCount}
                visibleColumns={columns.visibleColumns}
                onToggleExpanded={() => {
                  setEditingId(null);
                  setExpanded(expandedId === endpoint.id ? null : endpoint.id);
                }}
                onEdit={() => {
                  setEditingId(endpoint.id);
                  setExpanded(endpoint.id);
                }}
                onFinishEditing={() => {
                  setEditingId(null);
                  setExpanded(null);
                }}
                onDelete={() => setDeletingEndpoint(endpoint)}
                enterIndex={animateInitialRows ? index : undefined}
              />
            ))}
            {endpoints.data?.items.length === 0 ? (
              <RegistryMessage
                colSpan={columnCount}
                title={
                  hasFilters
                    ? t("filteredEmpty.title")
                    : t(
                        view === "managed"
                          ? "empty.providerTitle"
                          : "empty.title",
                      )
                }
                body={
                  hasFilters
                    ? t("filteredEmpty.body")
                    : t(
                        view === "managed"
                          ? "empty.providerBody"
                          : "empty.body",
                      )
                }
                action={
                  hasFilters ? (
                    <Button
                      size="sm"
                      variant="soft"
                      onClick={() => {
                        setExpandedId(null);
                        setEditingId(null);
                        setSelection(new Set());
                        replaceSearchParams(new URLSearchParams());
                      }}
                    >
                      {t("filteredEmpty.cta")}
                    </Button>
                  ) : view === "managed" ? (
                    <ConnectProviderButton
                      label={t("registry.connectProvider")}
                      size="sm"
                      variant="soft"
                    />
                  ) : (
                    <NewEndpointButton
                      label={t("registry.addEndpoint")}
                      size="sm"
                      variant="soft"
                    />
                  )
                }
              />
            ) : null}
          </TableBody>
        </Table>
      </section>

      <DeleteEndpointDialog
        endpoint={deletingEndpoint}
        open={deletingEndpoint !== null}
        onOpenChange={(open) => {
          if (!open) setDeletingEndpoint(null);
        }}
        onDeleted={(id) => {
          if (expandedId === id) {
            setEditingId(null);
            setExpanded(null);
          }
          setDeletingEndpoint(null);
        }}
      />

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("bulk.dialog.title")}</DialogTitle>
          </DialogHeader>
          <div className="rounded-lg bg-warning-soft p-4 text-sm text-warning">
            {t("bulk.dialog.bindingWarning")}
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="ghost">{t("cancel")}</Button>
            </DialogClose>
            <Button
              variant="destructive"
              disabled={bulkDelete.isPending}
              onClick={removeSelected}
            >
              {bulkDelete.isPending
                ? t("bulk.dialog.deleting")
                : t("bulk.dialog.confirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function EndpointLedgerRow({
  endpoint,
  showSelection,
  selected,
  onSelectedChange,
  expanded,
  editing,
  colSpan,
  visibleColumns,
  onToggleExpanded,
  onEdit,
  onFinishEditing,
  onDelete,
  enterIndex,
}: {
  endpoint: Endpoint;
  showSelection: boolean;
  selected: boolean;
  onSelectedChange: (checked: boolean) => void;
  expanded: boolean;
  editing: boolean;
  colSpan: number;
  visibleColumns: Set<EndpointColumnKey>;
  onToggleExpanded: () => void;
  onEdit: () => void;
  onFinishEditing: () => void;
  onDelete: () => void;
  enterIndex?: number;
}) {
  const t = useTranslations("dashboard.endpoints");
  const queryClient = useQueryClient();
  const updateEndpoint = useUpdateEndpointMutation();
  const checkHealth = useCheckEndpointHealthMutation();
  const managed = endpoint.origin_type === "provider";
  const expansionId = `endpoint-${endpoint.id}-details`;
  const [disclosurePresent, setDisclosurePresent] = useState(expanded);

  useEffect(() => {
    if (expanded) setDisclosurePresent(true);
  }, [expanded]);

  function setEnabled(checked: boolean) {
    updateEndpoint.mutate(
      {
        id: endpoint.id,
        input: { expected_version: endpoint.version, enabled: checked },
      },
      {
        onSuccess: () =>
          toast.success(t(checked ? "toast.enabled" : "toast.disabled")),
        onError: () => toast.error(t("toast.updateError")),
      },
    );
  }

  async function runHealthCheck() {
    try {
      await checkHealth.mutateAsync(endpoint.id);
      toast.success(t("health.checkComplete"));
    } catch {
      toast.error(t("health.checkError"));
    }
  }

  function prefetchDetails() {
    void queryClient.prefetchQuery(endpointDetailQueryOptions(endpoint.id));
  }

  return (
    <>
      <TableRow
        enterIndex={enterIndex}
        expanded={expanded}
        data-disclosure-closing={
          !expanded && disclosurePresent ? "true" : undefined
        }
      >
        {showSelection ? (
          <TableCell className="w-12">
            <Checkbox
              disabled={managed}
              checked={selected}
              onCheckedChange={(checked) => onSelectedChange(checked === true)}
              aria-label={t("bulk.selectEndpoint", { name: endpoint.name })}
            />
          </TableCell>
        ) : null}
        <TableCell className="min-w-0 overflow-hidden">
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls={expanded ? expansionId : undefined}
            disabled={editing}
            onClick={onToggleExpanded}
            onPointerEnter={prefetchDetails}
            onFocus={prefetchDetails}
            className="group/link flex w-full min-w-0 items-center gap-2 rounded-sm text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30 disabled:cursor-default"
          >
            <ChevronRight
              className="table-disclosure-chevron size-4 shrink-0 text-ink-400"
              aria-hidden
            />
            <span className="min-w-0 flex-1 truncate font-semibold text-ink-900 group-hover/link:text-brand">
              {endpoint.name}
            </span>
          </button>
        </TableCell>
        {visibleColumns.has("url") ? (
          <TableCell className="min-w-0">
            <CopyableEndpointUrl url={endpoint.effective_url ?? endpoint.url} />
          </TableCell>
        ) : null}
        {visibleColumns.has("network") ? (
          <TableCell>
            <span className="flex min-w-0 items-center gap-2">
              <ChainIcon
                chain={endpoint.chain}
                network={endpoint.network}
                className="size-4"
              />
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="truncate whitespace-nowrap font-medium">
                  {t(`chain.${endpoint.chain}`)}{" "}
                  <span className="text-ink-500">
                    · {t(`network.${endpoint.network}`)}
                  </span>
                </span>
                <span className="font-mono text-xs text-ink-500">
                  {t(`protocol.${endpoint.protocol}`)}
                </span>
              </span>
            </span>
          </TableCell>
        ) : null}
        {visibleColumns.has("health") ? (
          <TableCell>
            <EndpointHealthStatus health={endpoint.health} />
          </TableCell>
        ) : null}
        <TableCell align="right">
          <div className="flex items-center justify-end gap-1">
            <Switch
              size="sm"
              checked={endpoint.enabled}
              disabled={editing || updateEndpoint.isPending}
              onCheckedChange={setEnabled}
              aria-label={t(
                endpoint.enabled
                  ? "actions.disableEndpoint"
                  : "actions.enableEndpoint",
                { name: endpoint.name },
              )}
              className="mr-1"
            />
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              disabled={editing || checkHealth.isPending}
              aria-label={t("health.checkEndpoint", { name: endpoint.name })}
              title={t("health.check")}
              onClick={() => void runHealthCheck()}
            >
              {checkHealth.isPending ? (
                <LoaderCircle className="animate-spin" aria-hidden />
              ) : (
                <HeartPulse aria-hidden />
              )}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              disabled={editing}
              aria-label={t("actions.edit")}
              onClick={onEdit}
            >
              <Pencil aria-hidden />
            </Button>
            {!managed ? (
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                disabled={editing}
                className="text-ink-500 hover:bg-danger-soft hover:text-danger"
                aria-label={t("actions.delete")}
                onClick={onDelete}
              >
                <Trash2 aria-hidden />
              </Button>
            ) : null}
          </div>
        </TableCell>
      </TableRow>
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
            <EndpointDisclosureMotion>
              <div className="px-8 py-7">
                <EndpointRowExpansion
                  endpoint={endpoint}
                  editing={editing}
                  onFinishEditing={onFinishEditing}
                />
              </div>
            </EndpointDisclosureMotion>
          </TableExpandedRow>
        ) : null}
      </AnimatePresence>
    </>
  );
}

function EndpointDisclosureMotion({ children }: { children: React.ReactNode }) {
  const isPresent = useIsPresent();
  const motionPreset = useMotionPreset();

  return (
    <motion.div
      className="min-w-0"
      variants={emptyDetailVariants}
      initial={motionPreset.initial("initial")}
      animate="animate"
      exit="exit"
      transition={motionPreset.transition(
        isPresent ? transitionEnter : transitionExit,
      )}
    >
      {children}
    </motion.div>
  );
}
function RegistryLoading({ colSpan }: { colSpan: number }) {
  return (
    <>
      {SKELETON_ROWS.map((key) => (
        <TableRow key={key}>
          <TableCell colSpan={colSpan}>
            <div className="flex items-center gap-4">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-4 w-28" />
              <Skeleton className="ml-auto h-4 w-24" />
            </div>
          </TableCell>
        </TableRow>
      ))}
    </>
  );
}
function RegistryMessage({
  colSpan,
  title,
  body,
  action,
}: {
  colSpan: number;
  title: string;
  body: string;
  action: React.ReactNode;
}) {
  return (
    <TableRow className="h-full" data-enter="" data-table-state="message">
      <TableCell colSpan={colSpan} className="h-table-body-12">
        <div className="mx-auto flex h-full max-w-md flex-col items-center justify-center gap-2 text-center">
          <h2 className="text-lg font-semibold text-ink-900">{title}</h2>
          <p className="mb-3 text-sm text-ink-500">{body}</p>
          {action}
        </div>
      </TableCell>
    </TableRow>
  );
}

export { EndpointRegistry };
