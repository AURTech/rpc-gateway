"use client";

import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import type { RpcGatewayBase } from "@/api/gateways/client";
import type { RpcUsageRange } from "@/api/usage/client";
import { ChainGroup } from "@/components/ui/chain-group";
import { ChainIcon } from "@/components/ui/chain-icon";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useGatewaysQuery } from "@/hooks/use-gateways";
import { chainLabel, networkLabel } from "@/lib/rpc-chain";
import {
  DEFAULT_USAGE_RANGE,
  type UsageChartFilters,
  UsageRangeTabs,
} from "../../../usage/_components/usage-filter-bar";
import {
  CacheByMethodTrendCard,
  CacheTrendCard,
  LatencyTrendCard,
  MethodTrendCard,
  NetworkTrendCard,
  OverallTrendCard,
  TrafficTrendCard,
  type UsageScope,
} from "../../../usage/_components/usage-trend-cards";

// Same two-up grid the global Usage page uses; stacks to one column below xl.
const CHART_GRID = "grid grid-cols-1 gap-4 xl:grid-cols-2";

// The gateway list API caps `size` at 50; an app owns at most one gateway per
// (chain, network) pair (~21 across the registry), so one page covers them all.
const APP_GATEWAYS_SIZE = 50;

// `Select` needs string item values, so the cleared "all gateways" choice is a
// sentinel translated back to `undefined` for the scope.
const ALL = "__all__";

function gatewayDisplayName(gateway: RpcGatewayBase): string {
  return `${chainLabel(gateway.chain)} ${networkLabel(gateway.chain, gateway.network)}`;
}

/**
 * App detail "Metrics" tab: the app's call-level usage charts. Defaults to the
 * whole app (scoped by `app_id`); the gateway dropdown drills into a single
 * gateway. Only the supported call-level charts appear here — the upstream
 * charts are keyed by gateway/upstream and have no `app_id` dimension on the
 * backend, so they cannot be aggregated per app.
 */
export function AppUsagePanel({ appId }: { appId: string }) {
  const t = useTranslations("dashboard.apps.detail.metrics");

  const gatewaysQuery = useGatewaysQuery({
    app_id: appId,
    size: APP_GATEWAYS_SIZE,
  });
  const gateways = useMemo(
    () => gatewaysQuery.data?.items ?? [],
    [gatewaysQuery.data],
  );

  const [gatewayId, setGatewayId] = useState<string | undefined>(undefined);
  const [range, setRange] = useState<RpcUsageRange>(DEFAULT_USAGE_RANGE);
  const selectedGateway = gateways.find((gw) => gw.id === gatewayId);
  const gatewayChains = useMemo(
    () => gateways.map((gateway) => gateway.chain),
    [gateways],
  );

  // Default (no gateway) → aggregate the whole app; pick one → narrow to it.
  const scope = useMemo<UsageScope>(
    () => ({ app_id: appId, gateway_id: gatewayId }),
    [appId, gatewayId],
  );
  const filters = useMemo<UsageChartFilters>(() => ({ range }), [range]);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3">
        <Select
          value={gatewayId ?? ALL}
          onValueChange={(v) => setGatewayId(v === ALL ? undefined : v)}
        >
          <SelectTrigger
            aria-label={t("gatewayLabel")}
            className="h-9 w-64 max-w-full py-0 text-sm"
          >
            <span className="flex min-w-0 items-center gap-2">
              {selectedGateway ? (
                <ChainIcon
                  chain={selectedGateway.chain}
                  network={selectedGateway.network}
                  className="size-4 shrink-0"
                />
              ) : gatewayChains.length > 0 ? (
                <ChainGroup
                  chains={gatewayChains}
                  className="shrink-0"
                  max={5}
                />
              ) : null}
              {selectedGateway ? (
                <SelectValue />
              ) : (
                <span className="sr-only">{t("allGateways")}</span>
              )}
            </span>
          </SelectTrigger>
          {/* Cap the list height so a many-gateway app scrolls inside the
           * dropdown instead of filling the whole viewport. */}
          <SelectContent className="max-h-72 min-w-64">
            <SelectItem
              value={ALL}
              textValue={t("allGateways")}
              icon={
                gatewayChains.length > 0 ? (
                  <ChainGroup chains={gatewayChains} max={5} />
                ) : undefined
              }
            >
              <span className="sr-only">{t("allGateways")}</span>
            </SelectItem>
            {gateways.map((gw) => (
              <SelectItem
                key={gw.id}
                value={gw.id}
                icon={
                  <ChainIcon
                    chain={gw.chain}
                    network={gw.network}
                    className="size-4"
                  />
                }
              >
                {gatewayDisplayName(gw)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <UsageRangeTabs value={range} onChange={setRange} />
      </div>

      {/* Only this region scrolls; the gateway selector stays pinned above. */}
      <div className="no-scrollbar -mx-2 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-2 pt-1 pb-2">
        {gatewaysQuery.isPending ? (
          <UsageSkeleton />
        ) : (
          <>
            <div className={CHART_GRID}>
              <OverallTrendCard scope={scope} filters={filters} />
              <MethodTrendCard scope={scope} filters={filters} />
            </div>
            <div className={CHART_GRID}>
              <NetworkTrendCard scope={scope} filters={filters} />
              <CacheByMethodTrendCard scope={scope} filters={filters} />
            </div>
            <div className={CHART_GRID}>
              <CacheTrendCard scope={scope} filters={filters} />
              <TrafficTrendCard scope={scope} filters={filters} />
            </div>
            <div className={CHART_GRID}>
              <LatencyTrendCard scope={scope} filters={filters} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function UsageSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      {[0, 1, 2, 3].map((row) => (
        <div key={row} className={CHART_GRID}>
          {[0, 1].slice(0, row === 3 ? 1 : 2).map((col) => (
            <Skeleton key={col} className="h-72 w-full rounded-xl" />
          ))}
        </div>
      ))}
    </div>
  );
}
