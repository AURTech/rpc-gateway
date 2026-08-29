"use client";

import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";
import { Label, Pie, PieChart, Sector } from "recharts";
import type {
  PieSectorDataItem,
  PieSectorShapeProps,
} from "recharts/types/polar/Pie";
import { RPC_USAGE_RANGES, type RpcUsageRange } from "@/api/usage/client";
import {
  type ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { useEndpointsQuery } from "@/hooks/use-endpoints";
import { useUsageByEndpointQuery } from "@/hooks/use-usage";
import type { RpcChain, RpcNetwork } from "@/lib/rpc-chain";

const CHART_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--chart-6)",
  "var(--chart-7)",
  "var(--chart-8)",
] as const;
const OTHER_KEY = "__other__";

interface EndpointTrafficItem {
  endpointId: string;
  label: string;
  url: string | null;
  attempts: number;
  historical: boolean;
}

interface VisibleTrafficItem extends EndpointTrafficItem {
  color: string;
}

interface ChartItem {
  key: string;
  attempts: number;
  fill: string;
}

export function RouteTrafficDonut({
  gatewayId,
  routeId,
  chain,
  network,
  configuredEndpointIds,
}: {
  gatewayId: string;
  routeId: string | null;
  chain: RpcChain;
  network: RpcNetwork;
  configuredEndpointIds: string[];
}) {
  const t = useTranslations("dashboard.gateways.methodWorkbench.traffic");
  const [range, setRange] = useState<RpcUsageRange>("daily");
  const [selectedEndpointId, setSelectedEndpointId] = useState<string>("");
  const usage = useUsageByEndpointQuery(
    { gateway_id: gatewayId, route_id: routeId ?? "", range },
    { enabled: Boolean(routeId) },
  );
  const endpointsQuery = useEndpointsQuery({
    chain: [chain],
    network: [network],
    protocol: "jsonrpc",
    enabled: true,
    size: 100,
  });
  const endpointDetails = useMemo(
    () =>
      new Map(
        (endpointsQuery.data?.items ?? []).map((endpoint) => [
          endpoint.id,
          { name: endpoint.name, url: endpoint.url },
        ]),
      ),
    [endpointsQuery.data?.items],
  );
  const traffic = useMemo<VisibleTrafficItem[]>(() => {
    const counts = new Map(
      (usage.data?.items ?? []).map((item) => [
        item.endpoint_id,
        item.total_attempts,
      ]),
    );
    const ids = new Set([...configuredEndpointIds, ...counts.keys()]);
    return [...ids]
      .map((endpointId) => {
        const endpoint = endpointDetails.get(endpointId);
        return {
          endpointId,
          label: endpoint?.name ?? endpointId,
          url: endpoint?.url ?? null,
          attempts: counts.get(endpointId) ?? 0,
          historical: !configuredEndpointIds.includes(endpointId),
        };
      })
      .sort(
        (left, right) =>
          right.attempts - left.attempts ||
          left.label.localeCompare(right.label),
      )
      .map((item, index) => ({
        ...item,
        color: CHART_COLORS[index % CHART_COLORS.length],
      }));
  }, [configuredEndpointIds, endpointDetails, usage.data?.items]);

  useEffect(() => {
    if (traffic.length === 0) {
      setSelectedEndpointId("");
      return;
    }
    if (!traffic.some((item) => item.endpointId === selectedEndpointId)) {
      setSelectedEndpointId(traffic[0].endpointId);
    }
  }, [selectedEndpointId, traffic]);

  const visible = useMemo<VisibleTrafficItem[]>(
    () => visibleTraffic(traffic, selectedEndpointId),
    [selectedEndpointId, traffic],
  );
  const chartConfig = useMemo<ChartConfig>(() => {
    const config: ChartConfig = {
      attempts: { label: t("attempts") },
    };
    visible.forEach((item) => {
      config[item.endpointId] = {
        label: item.endpointId === OTHER_KEY ? t("other") : item.label,
        color: item.color,
      };
    });
    return config;
  }, [t, visible]);
  const chartData = useMemo<ChartItem[]>(
    () =>
      visible.map((item) => ({
        key: item.endpointId,
        attempts: item.attempts,
        fill: item.color,
      })),
    [visible],
  );
  const activeIndex = chartData.findIndex(
    (item) => item.key === selectedEndpointId,
  );
  const totalAttempts = usage.data?.total_attempts ?? 0;
  const selectPieSector = (data: PieSectorDataItem) => {
    const key = data.payload?.key;
    if (typeof key === "string" && key !== OTHER_KEY) {
      setSelectedEndpointId(key);
    }
  };

  const renderPieShape = ({
    index,
    outerRadius = 0,
    ...props
  }: PieSectorShapeProps) => {
    if (index === activeIndex) {
      return (
        <g>
          <Sector {...props} outerRadius={outerRadius + 8} />
          <Sector
            {...props}
            innerRadius={outerRadius + 10}
            outerRadius={outerRadius + 16}
          />
        </g>
      );
    }
    return <Sector {...props} outerRadius={outerRadius} />;
  };

  return (
    <div className="flex min-w-0 flex-col gap-5 rounded-2xl bg-surface px-4 py-4 sm:px-5 sm:py-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold text-ink-900">{t("title")}</h4>
          <p className="mt-0.5 text-2xs text-ink-500">{t("description")}</p>
        </div>
        <Tabs
          mode="segmented"
          value={range}
          onChange={setRange}
          options={RPC_USAGE_RANGES.map((value) => ({
            value,
            label: t(`range.${value}`),
          }))}
          ariaLabel={t("timeRange")}
        />
      </div>

      {!routeId ? (
        <TrafficEmpty>{t("saveFirst")}</TrafficEmpty>
      ) : usage.isLoading ? (
        <Skeleton className="mx-auto aspect-square w-full max-w-64 rounded-full" />
      ) : usage.isError ? (
        <TrafficEmpty danger>{t("error")}</TrafficEmpty>
      ) : traffic.length === 0 || totalAttempts === 0 ? (
        <TrafficEmpty>{t("empty")}</TrafficEmpty>
      ) : (
        <div className="grid items-center gap-6 lg:grid-cols-5 lg:gap-8">
          <div className="lg:col-span-2">
            <ChartContainer
              config={chartConfig}
              className="mx-auto aspect-square w-full max-w-80"
              initialDimension={{ width: 320, height: 320 }}
            >
              <PieChart>
                <ChartTooltip
                  cursor={false}
                  content={
                    <ChartTooltipContent
                      hideLabel
                      nameKey="key"
                      valueFormatter={(value) =>
                        t("attemptCount", { count: value })
                      }
                    />
                  }
                />
                <Pie
                  data={chartData}
                  dataKey="attempts"
                  nameKey="key"
                  innerRadius={76}
                  outerRadius={108}
                  strokeWidth={4}
                  cornerRadius={5}
                  shape={renderPieShape}
                  onClick={selectPieSector}
                >
                  <Label
                    content={({ viewBox }) => {
                      if (
                        !viewBox ||
                        !("cx" in viewBox) ||
                        !("cy" in viewBox)
                      ) {
                        return null;
                      }
                      return (
                        <text
                          x={viewBox.cx}
                          y={viewBox.cy}
                          textAnchor="middle"
                          dominantBaseline="middle"
                        >
                          <tspan
                            x={viewBox.cx}
                            y={(viewBox.cy ?? 0) - 5}
                            className="fill-ink-900 text-3xl font-bold"
                          >
                            {formatCompactAttempts(totalAttempts)}
                          </tspan>
                          <tspan
                            x={viewBox.cx}
                            y={(viewBox.cy ?? 0) + 22}
                            className="fill-ink-400 text-xs font-medium uppercase tracking-wide"
                          >
                            {t("attempts")}
                          </tspan>
                        </text>
                      );
                    }}
                  />
                </Pie>
              </PieChart>
            </ChartContainer>
          </div>
          <ul
            className="flex min-w-0 flex-col gap-2 lg:col-span-3"
            aria-label={t("breakdown")}
          >
            {visible.map((item) => (
              <TrafficBreakdownRow
                key={item.endpointId}
                item={item}
                totalAttempts={totalAttempts}
                selected={item.endpointId === selectedEndpointId}
                historicalLabel={t("historical")}
                otherLabel={t("other")}
                onSelect={() => {
                  if (item.endpointId !== OTHER_KEY) {
                    setSelectedEndpointId(item.endpointId);
                  }
                }}
              />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function TrafficBreakdownRow({
  item,
  totalAttempts,
  selected,
  historicalLabel,
  otherLabel,
  onSelect,
}: {
  item: VisibleTrafficItem;
  totalAttempts: number;
  selected: boolean;
  historicalLabel: string;
  otherLabel: string;
  onSelect: () => void;
}) {
  const percentage =
    totalAttempts > 0 ? (item.attempts / totalAttempts) * 100 : 0;
  const selectable = item.endpointId !== OTHER_KEY;
  return (
    <li>
      <button
        type="button"
        aria-pressed={selectable ? selected : undefined}
        onClick={onSelect}
        disabled={!selectable}
        className={
          selected
            ? "w-full rounded-xl bg-brand-soft px-3 py-3 text-left"
            : "w-full rounded-xl px-3 py-3 text-left hover:bg-ink-wash disabled:cursor-default disabled:hover:bg-transparent"
        }
      >
        <span className="flex min-w-0 items-start gap-2">
          <span
            className="size-2.5 shrink-0 rounded-full"
            style={{ backgroundColor: item.color }}
            aria-hidden
          />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold text-ink-800">
              {item.endpointId === OTHER_KEY ? otherLabel : item.label}
            </span>
            {item.url ? (
              <span className="mt-0.5 block truncate font-mono text-2xs text-ink-400">
                {item.url}
              </span>
            ) : null}
          </span>
          {item.historical ? (
            <span className="shrink-0 rounded-full bg-ink-wash px-2 py-0.5 text-2xs font-medium text-ink-500">
              {historicalLabel}
            </span>
          ) : null}
          <span className="shrink-0 text-xs font-semibold tabular-nums text-ink-700">
            {formatPercentage(percentage)}
          </span>
        </span>
        <span className="mt-2 flex items-center gap-3">
          <span className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-ink-wash">
            <span
              className="block h-full rounded-full"
              style={{
                width: `${Math.max(percentage, 1)}%`,
                backgroundColor: item.color,
              }}
            />
          </span>
          <span className="w-20 shrink-0 text-right font-mono text-xs tabular-nums text-ink-500">
            {item.attempts.toLocaleString()}
          </span>
        </span>
      </button>
    </li>
  );
}

function formatCompactAttempts(value: number): string {
  return new Intl.NumberFormat("en", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

function formatPercentage(value: number): string {
  return `${value >= 10 ? Math.round(value) : value.toFixed(1)}%`;
}

function visibleTraffic(
  traffic: VisibleTrafficItem[],
  selectedEndpointId: string,
): VisibleTrafficItem[] {
  if (traffic.length <= 8) return traffic;
  const selected = traffic.find(
    (item) => item.endpointId === selectedEndpointId,
  );
  const leaders = traffic.slice(
    0,
    selected && !traffic.slice(0, 7).includes(selected) ? 6 : 7,
  );
  if (selected && !leaders.includes(selected)) leaders.push(selected);
  const visibleIds = new Set(leaders.map((item) => item.endpointId));
  const otherAttempts = traffic
    .filter((item) => !visibleIds.has(item.endpointId))
    .reduce((total, item) => total + item.attempts, 0);
  return [
    ...leaders,
    {
      endpointId: OTHER_KEY,
      label: OTHER_KEY,
      url: null,
      attempts: otherAttempts,
      historical: false,
      color: CHART_COLORS[7],
    },
  ];
}

function TrafficEmpty({
  children,
  danger = false,
}: {
  children: string;
  danger?: boolean;
}) {
  return (
    <div className="flex min-h-64 items-center justify-center px-4 text-center">
      <p className={danger ? "text-sm text-danger" : "text-sm text-ink-400"}>
        {children}
      </p>
    </div>
  );
}
