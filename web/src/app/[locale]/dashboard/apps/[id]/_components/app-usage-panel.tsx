"use client";

import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import type { RpcGatewayBase } from "@/api/gateways/client";
import type { HttpApiRoute } from "@/api/http-api-routes/client";
import type { JsonRpcRoute } from "@/api/jsonrpc-routes/client";
import type {
  RpcUsageByRoute,
  RpcUsageRange,
  RpcUsageRouteItem,
} from "@/api/usage/client";
import { Badge } from "@/components/ui/badge";
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
import { Tabs } from "@/components/ui/tabs";
import { useGatewaysQuery } from "@/hooks/use-gateways";
import { useHttpApiRouteQuery } from "@/hooks/use-http-api-routes";
import { useDefaultRouteQuery, useMethodRoutesQuery } from "@/hooks/use-routes";
import { usageKeys, useUsageByRouteQuery } from "@/hooks/use-usage";
import { chainLabel, networkLabel } from "@/lib/rpc-chain";
import { cn } from "@/lib/utils";
import {
  DEFAULT_USAGE_RANGE,
  type UsageChartFilters,
  UsageToolbar,
} from "../../../usage/_components/usage-filter-bar";
import {
  AppRequestActivityTrendCard,
  CachePerformanceCard,
  LatencyTrendCard,
  MethodTrendCard,
  NetworkTrendCard,
  TrafficTrendCard,
  type UsageScope,
} from "../../../usage/_components/usage-trend-cards";
import { groupNetworks } from "./app-networks";
import {
  EndpointTrafficCard,
  type RouteUsageConfig,
} from "./endpoint-traffic-card";

const CHART_GRID = "grid grid-cols-1 gap-4 xl:grid-cols-2";
const APP_GATEWAYS_SIZE = 50;
const ALL = "__all__";
const USAGE_TABS = ["overview", "endpoints"] as const;

type UsageTab = (typeof USAGE_TABS)[number];

function gatewayDisplayName(gateway: RpcGatewayBase): string {
  return `${chainLabel(gateway.chain)} ${networkLabel(gateway.chain, gateway.network)}`;
}

export function AppUsagePanel({ appId }: { appId: string }) {
  const t = useTranslations("dashboard.apps.detail.metrics");
  const queryClient = useQueryClient();
  const isRefreshing = useIsFetching({ queryKey: usageKeys.all }) > 0;
  const gatewaysQuery = useGatewaysQuery({
    app_id: appId,
    size: APP_GATEWAYS_SIZE,
    sort: "DESC",
  });
  const gateways = useMemo(
    () =>
      groupNetworks(gatewaysQuery.data?.items ?? []).flatMap(
        (group) => group.gateways,
      ),
    [gatewaysQuery.data],
  );
  const [activeTab, setActiveTab] = useState<UsageTab>("overview");
  const [gatewayId, setGatewayId] = useState<string | undefined>();
  const [range, setRange] = useState<RpcUsageRange>(DEFAULT_USAGE_RANGE);
  const selectedGateway = gateways.find((gateway) => gateway.id === gatewayId);
  const gatewayChains = useMemo(
    () => gateways.map((gateway) => gateway.chain),
    [gateways],
  );
  const supportsJsonRpc =
    selectedGateway?.access_points.some(
      (point) => point.transport === "jsonrpc",
    ) ?? false;
  const supportsHttpApi =
    selectedGateway?.access_points.some(
      (point) => point.transport === "http_api",
    ) ?? false;
  const defaultRoute = useDefaultRouteQuery(
    supportsJsonRpc ? (gatewayId ?? null) : null,
  );
  const methodRoutes = useMethodRoutesQuery(
    supportsJsonRpc ? (gatewayId ?? null) : null,
  );
  const httpApiRoute = useHttpApiRouteQuery(
    supportsHttpApi ? (gatewayId ?? null) : null,
  );
  const routeOptions = useMemo(
    () =>
      buildRouteOptions(
        defaultRoute.data,
        methodRoutes.data?.items ?? [],
        httpApiRoute.data,
        {
          defaultRoute: t("routes.defaultRoute"),
          methods: (methods) => t("routes.methods", { methods }),
        },
      ),
    [defaultRoute.data, httpApiRoute.data, methodRoutes.data?.items, t],
  );
  const jsonRpcDefaultRoute = routeOptions.find(
    (route) => route.kind === "default",
  );
  const httpApiDefaultRoute = routeOptions.find(
    (route) => route.kind === "http_api",
  );
  const configuredMethodRoutes = routeOptions.filter(
    (route) => route.kind === "method",
  );
  const hasConfiguredRoutes = routeOptions.length > 0;
  const routesPending =
    Boolean(gatewayId) &&
    ((supportsJsonRpc && (defaultRoute.isPending || methodRoutes.isPending)) ||
      (supportsHttpApi && httpApiRoute.isPending));
  const routesError =
    Boolean(gatewayId) &&
    ((supportsJsonRpc && (defaultRoute.isError || methodRoutes.isError)) ||
      (supportsHttpApi && httpApiRoute.isError));

  useEffect(() => {
    if (activeTab === "endpoints" && !gatewayId && gateways.length > 0) {
      setGatewayId(gateways[0].id);
    }
  }, [activeTab, gatewayId, gateways]);

  const routeUsage = useUsageByRouteQuery({
    app_id: appId,
    gateway_id: gatewayId,
    range,
    limit: 100,
  });
  const scope = useMemo<UsageScope>(
    () => ({ app_id: appId, gateway_id: gatewayId }),
    [appId, gatewayId],
  );
  const filters = useMemo<UsageChartFilters>(() => ({ range }), [range]);

  const retryRoutes = () => {
    if (supportsJsonRpc) {
      void defaultRoute.refetch();
      void methodRoutes.refetch();
    }
    if (supportsHttpApi) void httpApiRoute.refetch();
  };

  const changeGateway = (value: string) => {
    setGatewayId(value === ALL ? undefined : value);
  };
  const refreshUsage = () => {
    void queryClient.invalidateQueries({ queryKey: usageKeys.all });
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <header className="flex shrink-0 flex-col gap-1.5">
        <h2 className="text-2xl font-bold tracking-tight text-ink-900">
          {t("title")}
        </h2>
        <p className="max-w-prose-narrow text-sm text-ink-500">
          {t("description")}
        </p>
      </header>

      <div className="flex flex-col gap-3 xl:flex-row xl:items-end">
        <div className="min-w-0 flex-1">
          <Tabs
            mode="tab"
            value={activeTab}
            onChange={setActiveTab}
            options={USAGE_TABS.map((value) => ({
              value,
              label: t(`tabs.${value}`),
            }))}
            ariaLabel={t("tabs.ariaLabel")}
            idBase="app-usage"
            variant="underline"
            size="lg"
          />
        </div>
        <div className="max-w-full self-end xl:shrink-0 xl:pb-2">
          <UsageToolbar
            range={range}
            onRangeChange={setRange}
            scopeFilter={
              <GatewaySelect
                gateways={gateways}
                gatewayChains={gatewayChains}
                selectedGateway={selectedGateway}
                value={gatewayId ?? (activeTab === "overview" ? ALL : "")}
                onChange={changeGateway}
                includeAll={activeTab === "overview"}
                label={t("gatewayLabel")}
                allLabel={t("allGateways")}
              />
            }
            onRefresh={refreshUsage}
            isRefreshing={isRefreshing}
          />
        </div>
      </div>

      <div
        data-app-usage-scroll
        className="no-scrollbar -mx-2 min-h-0 flex-1 overflow-y-auto px-2 pt-1 pb-2"
      >
        {gatewaysQuery.isPending ? (
          <section
            id="app-usage-panel"
            role="tabpanel"
            aria-labelledby={`app-usage-${activeTab}`}
          >
            <UsageSkeleton />
          </section>
        ) : activeTab === "overview" ? (
          <section
            id="app-usage-panel"
            role="tabpanel"
            aria-labelledby="app-usage-overview"
            className="flex flex-col gap-4"
          >
            <div className={CHART_GRID}>
              <AppRequestActivityTrendCard
                scope={scope}
                filters={filters}
                showDataThrough={false}
              />
              <MethodTrendCard
                scope={scope}
                filters={filters}
                showDataThrough={false}
              />
            </div>
            <div className={CHART_GRID}>
              <NetworkTrendCard
                scope={scope}
                filters={filters}
                showDataThrough={false}
              />
              <CachePerformanceCard
                scope={scope}
                filters={filters}
                showDataThrough={false}
              />
            </div>
            <div className={CHART_GRID}>
              <TrafficTrendCard
                scope={scope}
                filters={filters}
                showDataThrough={false}
              />
              <LatencyTrendCard
                scope={scope}
                filters={filters}
                showDataThrough={false}
              />
            </div>
          </section>
        ) : (
          <section
            id="app-usage-panel"
            role="tabpanel"
            aria-labelledby="app-usage-endpoints"
            className="flex min-w-0 flex-col gap-4"
          >
            {routesError ? (
              <RouteQueryErrorNotice onRetry={retryRoutes} />
            ) : null}
            {gatewayId ? (
              <>
                {jsonRpcDefaultRoute ? (
                  <EndpointTrafficCard
                    appId={appId}
                    gatewayId={gatewayId}
                    route={jsonRpcDefaultRoute}
                    range={range}
                  />
                ) : supportsJsonRpc && defaultRoute.isPending ? (
                  <Skeleton className="h-96 w-full rounded-xl" />
                ) : null}
                {httpApiDefaultRoute ? (
                  <EndpointTrafficCard
                    appId={appId}
                    gatewayId={gatewayId}
                    route={httpApiDefaultRoute}
                    range={range}
                  />
                ) : supportsHttpApi && httpApiRoute.isPending ? (
                  <Skeleton className="h-96 w-full rounded-xl" />
                ) : null}
                {!hasConfiguredRoutes && !routesPending && !routesError ? (
                  <div className="rounded-xl bg-surface px-5 py-8 text-center text-sm text-ink-500 shadow-section">
                    {t("routes.empty")}
                  </div>
                ) : null}
              </>
            ) : null}
            {gatewayId && configuredMethodRoutes.length > 0 ? (
              <section
                aria-labelledby="app-usage-method-routes"
                className="flex min-w-0 flex-col gap-4"
              >
                <h3
                  id="app-usage-method-routes"
                  className="text-sm font-semibold text-ink-900"
                >
                  {t("routes.methodRouteGroup", {
                    count: configuredMethodRoutes.length,
                  })}
                </h3>
                {configuredMethodRoutes.map((route) => (
                  <EndpointTrafficCard
                    key={route.id}
                    appId={appId}
                    gatewayId={gatewayId}
                    route={route}
                    range={range}
                    deferQuery
                  />
                ))}
              </section>
            ) : gatewayId && supportsJsonRpc && methodRoutes.isPending ? (
              <Skeleton className="h-96 w-full rounded-xl" />
            ) : null}
            {gatewayId ? (
              <RouteSummaryTable
                routes={routeOptions}
                gateways={gateways}
                data={routeUsage.data}
                isPending={routeUsage.isPending}
                isFetching={routeUsage.isFetching}
                isError={routeUsage.isError}
                onRetry={() => void routeUsage.refetch()}
                showGateway={false}
              />
            ) : null}
          </section>
        )}
      </div>
    </div>
  );
}

function GatewaySelect({
  gateways,
  gatewayChains,
  selectedGateway,
  value,
  onChange,
  includeAll = false,
  label,
  allLabel,
}: {
  gateways: RpcGatewayBase[];
  gatewayChains: RpcGatewayBase["chain"][];
  selectedGateway: RpcGatewayBase | undefined;
  value: string;
  onChange: (value: string) => void;
  includeAll?: boolean;
  label: string;
  allLabel: string;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger
        aria-label={label}
        className={cn(
          "h-8 max-w-full rounded-full px-3.5 py-0 text-xs text-ink-700 [&>svg]:hidden",
          includeAll && !selectedGateway && gatewayChains.length > 0
            ? "w-auto"
            : "w-52",
        )}
      >
        <span className="flex min-w-0 items-center gap-2">
          {selectedGateway ? (
            <ChainIcon
              chain={selectedGateway.chain}
              network={selectedGateway.network}
              className="size-4 shrink-0"
            />
          ) : gatewayChains.length > 0 ? (
            <ChainGroup chains={gatewayChains} className="shrink-0" max={5} />
          ) : null}
          {selectedGateway ? (
            <SelectValue />
          ) : includeAll && gatewayChains.length > 0 ? (
            <span className="sr-only">{allLabel}</span>
          ) : (
            <span className="truncate">{label}</span>
          )}
        </span>
      </SelectTrigger>
      <SelectContent className="max-h-72 min-w-64 [&_[data-slot=select-scroll-down-button]]:hidden [&_[data-slot=select-scroll-up-button]]:hidden">
        {includeAll && gatewayChains.length > 0 ? (
          <SelectItem
            value={ALL}
            textValue={allLabel}
            icon={
              gatewayChains.length > 0 ? (
                <ChainGroup chains={gatewayChains} max={5} />
              ) : undefined
            }
          >
            <span className="sr-only">{allLabel}</span>
          </SelectItem>
        ) : null}
        {gateways.map((gateway) => (
          <SelectItem
            key={gateway.id}
            value={gateway.id}
            icon={
              <ChainIcon
                chain={gateway.chain}
                network={gateway.network}
                className="size-4"
              />
            }
          >
            {gatewayDisplayName(gateway)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function buildRouteOptions(
  defaultRoute: JsonRpcRoute | undefined,
  methodRoutes: JsonRpcRoute[],
  httpApiRoute: HttpApiRoute | undefined,
  labels: {
    defaultRoute: string;
    methods: (methods: string) => string;
  },
): RouteUsageConfig[] {
  const routes: RouteUsageConfig[] = [];
  if (defaultRoute) {
    routes.push(toRouteConfig(defaultRoute, labels.defaultRoute, "default"));
  }
  for (const route of methodRoutes) {
    routes.push(
      toRouteConfig(route, labels.methods(route.methods.join(", ")), "method"),
    );
  }
  if (httpApiRoute) {
    routes.push(toRouteConfig(httpApiRoute, labels.defaultRoute, "http_api"));
  }
  return routes;
}

function toRouteConfig(
  route: JsonRpcRoute | HttpApiRoute,
  label: string,
  kind: RouteUsageConfig["kind"],
): RouteUsageConfig {
  return {
    id: route.id,
    label,
    kind,
    strategy: route.strategy.type,
  };
}

export function RouteQueryErrorNotice({ onRetry }: { onRetry: () => void }) {
  const t = useTranslations("dashboard.apps.detail.metrics");
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-warning-soft px-5 py-3 text-xs text-warning shadow-section"
    >
      <p>{t("routes.error")}</p>
      <button
        type="button"
        onClick={onRetry}
        className="rounded-md bg-surface px-3 py-1.5 font-semibold text-ink-700 transition-colors hover:text-ink-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        {t("routes.retry")}
      </button>
    </div>
  );
}

export function RouteSummaryTable({
  routes,
  gateways,
  data,
  isPending,
  isFetching,
  isError,
  onRetry,
  showGateway,
}: {
  routes: RouteUsageConfig[];
  gateways: RpcGatewayBase[];
  data: RpcUsageByRoute | undefined;
  isPending: boolean;
  isFetching: boolean;
  isError: boolean;
  onRetry: () => void;
  showGateway: boolean;
}) {
  const t = useTranslations("dashboard.apps.detail.metrics");
  const routeById = new Map(routes.map((route) => [route.id, route]));
  const gatewayById = new Map(gateways.map((gateway) => [gateway.id, gateway]));

  return (
    <section
      aria-busy={isFetching}
      className="rounded-xl bg-surface px-5 py-4 shadow-section"
    >
      <h3 className="text-sm font-semibold text-ink-900">
        {t("routeSummary.title")}
      </h3>
      {isError ? (
        <div
          role="alert"
          className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-ink-wash px-3 py-2"
        >
          <p className="text-xs font-medium text-ink-800">
            {t("routeSummary.error")}
          </p>
          <button
            type="button"
            onClick={onRetry}
            className="rounded-md bg-surface px-3 py-1.5 text-xs font-semibold text-ink-700 transition-colors hover:text-ink-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            {t("routeSummary.retry")}
          </button>
        </div>
      ) : null}
      {isPending && !data ? (
        <output aria-live="polite" className="mt-3 block">
          <span className="sr-only">{t("routeSummary.loading")}</span>
          <Skeleton aria-hidden className="h-28 w-full rounded-lg" />
        </output>
      ) : !data || (isError && data.items.length === 0) ? null : data.items
          .length === 0 ? (
        <p className="mt-3 rounded-lg bg-ink-wash px-3 py-6 text-center text-xs text-ink-500">
          {t("routeSummary.empty")}
        </p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-192 text-left text-xs">
            <thead className="text-ink-500">
              <tr>
                {showGateway ? (
                  <th className="pb-2 font-medium">
                    {t("routeSummary.gateway")}
                  </th>
                ) : null}
                <th className="pb-2 font-medium">{t("routeSummary.route")}</th>
                <th className="pb-2 font-medium">
                  {t("routeSummary.strategy")}
                </th>
                <th className="pb-2 font-medium">
                  {t("routeSummary.requests")}
                </th>
                <th className="pb-2 font-medium">
                  {t("routeSummary.attemptsPerRequest")}
                </th>
                <th className="pb-2 font-medium">
                  {t("routeSummary.multiAttemptRate")}
                </th>
                <th className="pb-2 font-medium">
                  {t("routeSummary.exhausted")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-wash">
              {data.items.map((summary: RpcUsageRouteItem) => {
                const route = routeById.get(summary.route_id);
                const gateway = gatewayById.get(summary.gateway_id);
                return (
                  <tr key={`${summary.gateway_id}:${summary.route_id}`}>
                    {showGateway ? (
                      <td className="py-2.5 pr-4 font-medium text-ink-900">
                        {gateway?.name ?? summary.gateway_id}
                      </td>
                    ) : null}
                    <td className="py-2.5 pr-4 font-medium text-ink-900">
                      <span className="flex items-center gap-2">
                        <span>{route?.label ?? summary.route_id}</span>
                        {route ? (
                          <Badge variant="neutral">
                            {t(
                              route.kind === "http_api"
                                ? "routes.protocols.httpApi"
                                : "routes.protocols.jsonRpc",
                            )}
                          </Badge>
                        ) : null}
                      </span>
                    </td>
                    <td className="py-2.5 pr-4 text-ink-700">
                      {route
                        ? t(`routes.strategies.${route.strategy}`)
                        : t("routeSummary.unknown")}
                    </td>
                    <td className="py-2.5 pr-4 font-mono tabular-nums text-ink-700">
                      {summary.routed_requests.toLocaleString()}
                    </td>
                    <td className="py-2.5 pr-4 font-mono tabular-nums text-ink-700">
                      {summary.avg_attempts.toLocaleString(undefined, {
                        maximumFractionDigits: 2,
                      })}
                    </td>
                    <td className="py-2.5 pr-4 font-mono tabular-nums text-ink-700">
                      {formatRate(summary.multi_attempt_rate)}
                    </td>
                    <td className="py-2.5 font-mono tabular-nums text-ink-700">
                      {summary.exhausted_requests.toLocaleString()}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function formatRate(value: number): string {
  return new Intl.NumberFormat(undefined, {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);
}

function UsageSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      {[0, 1, 2].map((row) => (
        <div key={row} className={CHART_GRID}>
          {[0, 1].map((col) => (
            <Skeleton key={col} className="h-72 w-full rounded-xl" />
          ))}
        </div>
      ))}
    </div>
  );
}
