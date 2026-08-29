"use client";

import { ChevronDown, RefreshCw, Search } from "lucide-react";
import { useTranslations } from "next-intl";
import { type ReactNode, useMemo, useState } from "react";

import { RPC_USAGE_RANGES, type RpcUsageRange } from "@/api/usage/client";
import { Button } from "@/components/ui/button";
import { ChainGroup } from "@/components/ui/chain-group";
import { ChainIcon } from "@/components/ui/chain-icon";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Toolbar, ToolbarGroup } from "@/components/ui/toolbar";
import {
  chainLabel,
  networkLabel,
  networksFor,
  RPC_CHAINS,
  type RpcChain,
  type RpcNetwork,
} from "@/lib/rpc-chain";
import { cn } from "@/lib/utils";

const TRIGGER_CLASS =
  "inline-flex h-8 items-center gap-1.5 rounded-full bg-ink-wash px-3.5 text-xs font-medium text-ink-700 transition-colors active:scale-95 hover:bg-stripe focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30";

export const DEFAULT_USAGE_RANGE: RpcUsageRange = "weekly";
export const DEFAULT_USAGE_FILTERS: UsageChartFilters = {
  range: DEFAULT_USAGE_RANGE,
};

const SCOPE_ALL = "__all__";
const SCOPE_NETWORK_PREFIX = "network:";
const ALL_SCOPE_CHAINS = [...RPC_CHAINS];

// Scope dimensions shared by every Usage chart. Uses the snake-cased
// `gateway_id` / `app_id` so they can be spread straight into the query hooks.
// The global Usage page only sets chain/network (account-wide view); the
// per-app usage panel reuses the same charts by supplying `app_id` (and an
// optional `gateway_id` to drill into one gateway).
export type UsageScope = {
  chain?: RpcChain;
  network?: RpcNetwork;
  gateway_id?: string;
  app_id?: string;
};

export type UsageChartFilters = {
  range: RpcUsageRange;
  chain?: RpcChain;
  network?: RpcNetwork;
};

// The page owns one range + one chain/network scope for every chart and the KPI
// strip, so this toolbar is the only place either filter is offered.
export function UsageGlobalToolbar({
  value,
  onChange,
  onRefresh,
  isRefreshing,
}: {
  value: UsageChartFilters;
  onChange: (next: UsageChartFilters) => void;
  onRefresh: () => void;
  isRefreshing: boolean;
}) {
  return (
    <UsageToolbar
      range={value.range}
      onRangeChange={(range) => onChange({ ...value, range })}
      scopeFilter={
        <UsageScopeFilters
          value={value}
          onChange={(next) =>
            onChange({ ...value, chain: next.chain, network: next.network })
          }
        />
      }
      onRefresh={onRefresh}
      isRefreshing={isRefreshing}
    />
  );
}

// Shared Usage toolbar shell. Account Usage supplies the chain/network picker;
// App Usage supplies its app-scoped gateway picker, while range and refresh
// behavior remain identical across both surfaces.
export function UsageToolbar({
  range,
  onRangeChange,
  scopeFilter,
  onRefresh,
  isRefreshing,
}: {
  range: RpcUsageRange;
  onRangeChange: (next: RpcUsageRange) => void;
  scopeFilter: ReactNode;
  onRefresh: () => void;
  isRefreshing: boolean;
}) {
  const t = useTranslations("dashboard.usage");

  return (
    <Toolbar role="toolbar" aria-label={t("filters.toolbarAriaLabel")}>
      <ToolbarGroup>
        <UsageRangeSelect value={range} onChange={onRangeChange} />
        {scopeFilter}
      </ToolbarGroup>
      <ToolbarGroup align="end">
        <Button
          type="button"
          variant="pill-secondary"
          size="sm"
          className="rounded-full"
          onClick={onRefresh}
          disabled={isRefreshing}
        >
          <RefreshCw
            className={cn("size-3.5", isRefreshing && "animate-spin")}
            aria-hidden
          />
          {t("filters.refresh")}
        </Button>
      </ToolbarGroup>
    </Toolbar>
  );
}

// Dropdown form of the range control. Its options name the complete window
// ("Last 7 days") so the selected state remains clear on both Usage surfaces.
export function UsageRangeSelect({
  value,
  onChange,
}: {
  value: RpcUsageRange;
  onChange: (next: RpcUsageRange) => void;
}) {
  const t = useTranslations("dashboard.usage");
  const rangeOptions = useMemo(
    () =>
      RPC_USAGE_RANGES.map((range) => ({
        value: range,
        label: t(`filters.rangeWindows.${range}`),
      })),
    [t],
  );
  const selected = rangeOptions.find((o) => o.value === value);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={t("filters.rangeAriaLabel")}
          className={cn(TRIGGER_CLASS, "text-brand")}
        >
          {selected?.label ?? t("filters.rangeAriaLabel")}
          <ChevronDown className="size-3 text-brand" aria-hidden />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-36">
        <DropdownMenuRadioGroup
          value={value}
          onValueChange={(next) => onChange(next as RpcUsageRange)}
        >
          {rangeOptions.map((opt) => (
            <DropdownMenuRadioItem key={opt.value} value={opt.value}>
              {opt.label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

type ScopeOption = {
  value: string;
  chain: RpcChain;
  network: RpcNetwork;
  label: string;
  searchText: string;
};

// Combined chain/network scope. The menu is a flat list of chain-network pairs
// so users do not have to step through separate chain and network controls.
export function UsageScopeFilters({
  value,
  onChange,
  triggerClassName,
}: {
  value: UsageScope;
  onChange: (next: UsageScope) => void;
  triggerClassName?: string;
}) {
  const t = useTranslations("dashboard.usage");
  const triggerLabel = `${t("filters.chainLabel")} / ${t("filters.networkLabel")}`;
  const selectedChain = value.chain;
  const selectedValue = scopeValueFrom(value);
  const display = scopeDisplay(value);
  const [search, setSearch] = useState("");
  const options = useMemo<ScopeOption[]>(() => buildScopeOptions(), []);
  const filteredOptions = useMemo(() => {
    const query = normalizeSearch(search);
    if (!query) return options;
    return options.filter((option) => option.searchText.includes(query));
  }, [options, search]);

  return (
    <DropdownMenu onOpenChange={(open) => !open && setSearch("")}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={triggerLabel}
          className={cn(
            TRIGGER_CLASS,
            selectedChain && "text-brand",
            triggerClassName,
          )}
        >
          {selectedChain ? (
            <span aria-hidden>
              <ChainIcon chain={selectedChain} className="size-4 shrink-0" />
            </span>
          ) : null}
          {display ?? t("filters.allNetworks")}
          <ChevronDown
            className={cn(
              "size-3",
              selectedChain ? "text-brand" : "text-ink-400",
            )}
            aria-hidden
          />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-72 p-0">
        <div className="border-table-frame border-b p-2">
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-ink-400"
              aria-hidden
            />
            <input
              type="search"
              aria-label={t("filters.searchAria")}
              placeholder={t("filters.searchPlaceholder")}
              value={search}
              onChange={(event) => setSearch(event.currentTarget.value)}
              onKeyDown={(event) => event.stopPropagation()}
              className="h-8 w-full rounded-full bg-ink-wash pl-8 pr-3 text-xs font-medium text-ink-900 outline-none placeholder:text-ink-400 focus:bg-surface focus-visible:ring-2 focus-visible:ring-brand/30"
            />
          </div>
        </div>
        <div className="max-h-80 overflow-y-auto p-1">
          <DropdownMenuRadioGroup
            value={selectedValue}
            onValueChange={(next) => onChange(parseScopeValue(value, next))}
          >
            <DropdownMenuRadioItem value={SCOPE_ALL} className="min-h-9 gap-2">
              <span aria-hidden>
                <ChainGroup chains={ALL_SCOPE_CHAINS} max={5} />
              </span>
              {t("filters.allNetworks")}
            </DropdownMenuRadioItem>
            {filteredOptions.length > 0 ? (
              filteredOptions.map((option) => (
                <DropdownMenuRadioItem
                  key={option.value}
                  value={option.value}
                  className="gap-2"
                >
                  <span aria-hidden>
                    <ChainIcon
                      chain={option.chain}
                      className="size-4 shrink-0"
                    />
                  </span>
                  {option.label}
                </DropdownMenuRadioItem>
              ))
            ) : (
              <div className="px-3 py-6 text-center text-xs text-ink-500">
                {t("filters.noNetworkMatches")}
              </div>
            )}
          </DropdownMenuRadioGroup>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function networkScopeValue(chain: RpcChain, network: RpcNetwork): string {
  return `${SCOPE_NETWORK_PREFIX}${chain}:${network}`;
}

function scopeValueFrom(value: UsageScope): string {
  if (value.chain && value.network) {
    return networkScopeValue(value.chain, value.network);
  }
  return SCOPE_ALL;
}

function parseScopeValue(current: UsageScope, value: string): UsageScope {
  if (value === SCOPE_ALL) {
    return { ...current, chain: undefined, network: undefined };
  }

  if (value.startsWith(SCOPE_NETWORK_PREFIX)) {
    const [chain, network] = value
      .slice(SCOPE_NETWORK_PREFIX.length)
      .split(":") as [RpcChain, RpcNetwork];
    return { ...current, chain, network };
  }

  return current;
}

function scopeDisplay(value: UsageScope): string | null {
  if (value.chain && value.network) {
    return `${chainLabel(value.chain)} · ${networkLabel(value.chain, value.network)}`;
  }
  if (value.chain) return chainLabel(value.chain);
  return null;
}

function buildScopeOptions(): ScopeOption[] {
  return RPC_CHAINS.flatMap((chain) =>
    networksFor(chain).map((network) => {
      const label = `${chainLabel(chain)} · ${networkLabel(chain, network)}`;
      return {
        value: networkScopeValue(chain, network),
        chain,
        network,
        label,
        searchText: normalizeSearch(
          `${label} ${chain} ${network} ${chainLabel(chain)} ${networkLabel(chain, network)}`,
        ),
      };
    }),
  );
}

function normalizeSearch(value: string): string {
  return value.trim().toLowerCase();
}
