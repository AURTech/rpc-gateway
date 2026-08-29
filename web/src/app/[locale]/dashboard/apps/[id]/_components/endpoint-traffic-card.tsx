"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";

import type { RpcUsageByEndpoint, RpcUsageRange } from "@/api/usage/client";
import { formatCompactNumber } from "@/components/dashboard/usage-trend-chart";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  type ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { useUsageByEndpointQuery } from "@/hooks/use-usage";
import {
  CHART_DRAW_EASING,
  CHART_DRAW_MS,
  CHART_SERIES_STAGGER_MS,
} from "@/lib/motion";
import { cn } from "@/lib/utils";

const ENDPOINT_QUERY_LIMIT = 100;
const ENDPOINT_DISPLAY_LIMIT = 5;
const COLORS = [
  "var(--chart-1)",
  "var(--chart-9)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--chart-6)",
] as const;
const OTHER_COLOR = "var(--ink-400)";
const ENDPOINT_VIEWS = ["attempt_count", "traffic_share"] as const;

type EndpointView = (typeof ENDPOINT_VIEWS)[number];

export interface RouteUsageConfig {
  id: string;
  label: string;
  kind: "default" | "method" | "http_api";
  strategy: "priority_failover" | "load_balance";
}

interface EndpointTrafficCardProps {
  appId: string;
  gatewayId: string;
  route: RouteUsageConfig;
  range: RpcUsageRange;
  deferQuery?: boolean;
}

interface EndpointSeriesMeta {
  key: string;
  label: string;
  historical: boolean;
  totalAttempts: number;
  color: string;
}

type ChartRow = { bucket: string; total: number } & Record<
  string,
  number | string
>;

type EndpointItem = RpcUsageByEndpoint["items"][number];

function chartModel(
  data: RpcUsageByEndpoint | undefined,
  otherLabel: string,
  coverageStartAt?: string | null,
) {
  if (!data) {
    return {
      rows: [] as ChartRow[],
      meta: [] as EndpointSeriesMeta[],
      totalAttempts: 0,
    };
  }

  const classifiedAttemptsForItem = (item: EndpointItem) =>
    coverageStartAt
      ? item.points.reduce(
          (total, point) => total + point.first_attempts + point.retry_attempts,
          0,
        )
      : 0;
  const rankedItems = [...data.items].sort(
    (left, right) =>
      classifiedAttemptsForItem(right) - classifiedAttemptsForItem(left),
  );
  const visibleItems = rankedItems.slice(0, ENDPOINT_DISPLAY_LIMIT);
  const groupedItems = rankedItems.slice(ENDPOINT_DISPLAY_LIMIT);
  const meta: EndpointSeriesMeta[] = visibleItems.map((item, index) => ({
    key: `endpoint${index}`,
    label: item.name,
    historical: item.historical,
    totalAttempts: item.total_attempts,
    color: COLORS[index],
  }));
  const otherTotalAttempts =
    (coverageStartAt
      ? data.other_points.reduce(
          (total, point) => total + point.first_attempts + point.retry_attempts,
          0,
        )
      : 0) +
    groupedItems.reduce(
      (total, item) => total + classifiedAttemptsForItem(item),
      0,
    );
  if (otherTotalAttempts > 0) {
    meta.push({
      key: "other",
      label: otherLabel,
      historical: false,
      totalAttempts: otherTotalAttempts,
      color: OTHER_COLOR,
    });
  }

  const rowsByBucket = new Map<string, ChartRow>();
  const coverageStartMs = coverageStartAt ? Date.parse(coverageStartAt) : null;
  const addPoint = (key: string, bucket: string, attempts: number) => {
    const row = rowsByBucket.get(bucket) ?? { bucket, total: 0 };
    row[key] = (typeof row[key] === "number" ? row[key] : 0) + attempts;
    row.total += attempts;
    rowsByBucket.set(bucket, row);
  };
  visibleItems.forEach((item, index) => {
    item.points.forEach((point) => {
      addPoint(
        `endpoint${index}`,
        point.bucket_start,
        coverageStartAt ? point.first_attempts + point.retry_attempts : 0,
      );
    });
  });
  if (otherTotalAttempts > 0) {
    data.other_points.forEach((point) => {
      addPoint(
        "other",
        point.bucket_start,
        coverageStartAt ? point.first_attempts + point.retry_attempts : 0,
      );
    });
    groupedItems.forEach((item) => {
      item.points.forEach((point) => {
        addPoint(
          "other",
          point.bucket_start,
          coverageStartAt ? point.first_attempts + point.retry_attempts : 0,
        );
      });
    });
  }
  const allRows = [...rowsByBucket.values()].sort((left, right) =>
    left.bucket < right.bucket ? -1 : 1,
  );
  const coverageAfterWindow =
    coverageStartMs != null &&
    Number.isFinite(coverageStartMs) &&
    coverageStartMs >= Date.parse(data.end_at);
  const coverageRowIndex =
    coverageStartMs != null && Number.isFinite(coverageStartMs)
      ? allRows.findIndex((_row, index) => {
          const next = allRows[index + 1];
          return !next || Date.parse(next.bucket) > coverageStartMs;
        })
      : 0;
  const rows = coverageAfterWindow
    ? []
    : allRows.slice(Math.max(coverageRowIndex, 0));
  const attemptsByKey = new Map<string, number>();
  for (const row of rows) {
    for (const item of meta) {
      const value = row[item.key];
      if (typeof value === "number") {
        attemptsByKey.set(item.key, (attemptsByKey.get(item.key) ?? 0) + value);
      }
    }
  }
  const coveredMeta = meta
    .map((item) => ({
      ...item,
      totalAttempts: attemptsByKey.get(item.key) ?? 0,
    }))
    .filter((item) => item.totalAttempts > 0);

  return {
    rows,
    meta: coveredMeta,
    totalAttempts: rows.reduce((total, row) => total + row.total, 0),
  };
}

function useNearViewport(deferQuery: boolean) {
  const cardRef = useRef<HTMLDivElement | null>(null);
  const [isNearViewport, setIsNearViewport] = useState(!deferQuery);

  useEffect(() => {
    if (!deferQuery) return;
    const element = cardRef.current;
    if (!element || typeof IntersectionObserver === "undefined") {
      setIsNearViewport(true);
      return;
    }

    const scrollRoot = element.closest<HTMLElement>("[data-app-usage-scroll]");
    const observer = new IntersectionObserver(
      ([entry]) => setIsNearViewport(entry?.isIntersecting ?? false),
      { root: scrollRoot, rootMargin: "400px 0px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [deferQuery]);

  return { cardRef, queryEnabled: !deferQuery || isNearViewport };
}

export function EndpointTrafficCard({
  appId,
  gatewayId,
  route,
  range,
  deferQuery = false,
}: EndpointTrafficCardProps) {
  const t = useTranslations("dashboard.apps.detail.metrics.endpointTraffic");
  const routeLabels = useTranslations("dashboard.apps.detail.metrics.routes");
  const common = useTranslations("dashboard.usage");
  const locale = useLocale();
  const descriptionId = useId();
  const gradientId = useId().replace(/:/g, "");
  const [view, setView] = useState<EndpointView>("attempt_count");
  const { cardRef, queryEnabled } = useNearViewport(deferQuery);
  const query = useUsageByEndpointQuery(
    {
      app_id: appId,
      gateway_id: gatewayId,
      route_id: route.id,
      range,
      limit: ENDPOINT_QUERY_LIMIT,
    },
    { enabled: queryEnabled },
  );
  const coverageStartAt = query.data?.classification_coverage_start_at;
  const model = useMemo(
    () => chartModel(query.data, t("other"), coverageStartAt),
    [coverageStartAt, query.data, t],
  );
  const config = useMemo<ChartConfig>(
    () =>
      Object.fromEntries(
        model.meta.map((item) => [
          item.key,
          { label: item.label, color: item.color },
        ]),
      ),
    [model.meta],
  );
  const formatTime = useMemo(
    () =>
      new Intl.DateTimeFormat(locale, {
        month: "short",
        day: "2-digit",
        hour: range === "weekly" || range === "monthly" ? undefined : "2-digit",
        minute:
          range === "weekly" || range === "monthly" ? undefined : "2-digit",
        hour12: false,
      }),
    [locale, range],
  );
  const totalAttempts = model.totalAttempts;
  const protocolLabel = routeLabels(
    route.kind === "http_api" ? "protocols.httpApi" : "protocols.jsonRpc",
  );
  const strategyLabel = routeLabels(`strategies.${route.strategy}`);
  const canCompareTrafficShare = model.meta.length > 1;
  const effectiveView = canCompareTrafficShare ? view : "attempt_count";

  return (
    <Card ref={cardRef} className="min-w-0 gap-4">
      <CardHeader className="has-data-[slot=card-action]:grid-cols-1 sm:has-data-[slot=card-action]:grid-cols-[1fr_auto]">
        <CardTitle className="flex min-w-0 flex-wrap items-center gap-2 text-lg text-ink-900">
          <span className="min-w-0 break-words">{route.label}</span>
          <Badge variant="neutral">{protocolLabel}</Badge>
          <Badge variant="neutral">{strategyLabel}</Badge>
        </CardTitle>
        <CardDescription id={descriptionId} className="text-xs">
          {t("subhead")}
        </CardDescription>
        {canCompareTrafficShare ? (
          <CardAction className="col-start-1 row-start-3 justify-self-start sm:col-start-2 sm:row-span-2 sm:row-start-1 sm:justify-self-end">
            <Tabs
              mode="segmented"
              value={effectiveView}
              onChange={setView}
              options={ENDPOINT_VIEWS.map((value) => ({
                value,
                label: t(`views.${value}`),
              }))}
              ariaLabel={t("viewAriaLabel")}
            />
          </CardAction>
        ) : null}
      </CardHeader>
      <CardContent>
        {query.isPending && model.meta.length === 0 ? (
          <output aria-live="polite" className="block">
            <span className="sr-only">{t("loading")}</span>
            <Skeleton aria-hidden className="h-72 w-full rounded-xl" />
          </output>
        ) : query.isError && model.meta.length === 0 ? (
          <div
            role="alert"
            className="flex h-72 items-center justify-between gap-4 rounded-xl bg-ink-wash p-5"
          >
            <p className="text-md font-medium text-ink-900">
              {common("error.title")}
            </p>
            <button
              type="button"
              onClick={() => query.refetch()}
              className="rounded-md bg-surface px-3 py-1.5 text-xs font-semibold text-ink-700 transition-colors hover:text-ink-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              {common("error.retry")}
            </button>
          </div>
        ) : model.meta.length === 0 || totalAttempts === 0 ? (
          <div className="flex h-72 items-center justify-center rounded-xl bg-ink-wash text-md text-ink-500">
            {t("empty")}
          </div>
        ) : (
          <figure
            aria-label={t("chartAriaLabel", {
              route: route.label,
              protocol: protocolLabel,
              strategy: strategyLabel,
            })}
            aria-describedby={descriptionId}
            aria-busy={query.isFetching}
            className={cn(
              "space-y-4 rounded-lg transition-opacity",
              query.isFetching && "opacity-60",
            )}
          >
            <ChartContainer config={config} className="h-72 w-full aspect-auto">
              <AreaChart
                accessibilityLayer
                data={model.rows}
                margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
                stackOffset={
                  effectiveView === "traffic_share" ? "expand" : "none"
                }
              >
                <defs>
                  {model.meta.map((item) => (
                    <linearGradient
                      key={item.key}
                      id={`${gradientId}-${item.key}`}
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop
                        offset="5%"
                        stopColor={item.color}
                        stopOpacity={0.8}
                      />
                      <stop
                        offset="95%"
                        stopColor={item.color}
                        stopOpacity={0.1}
                      />
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid
                  vertical={false}
                  stroke="var(--ink-900)"
                  strokeOpacity={0.06}
                />
                <XAxis
                  dataKey="bucket"
                  tickFormatter={(value: string) =>
                    formatTime.format(new Date(value))
                  }
                  tickLine={false}
                  axisLine={false}
                  minTickGap={28}
                />
                <YAxis
                  domain={
                    effectiveView === "traffic_share" ? [0, 1] : [0, "auto"]
                  }
                  ticks={
                    effectiveView === "traffic_share"
                      ? [0, 0.25, 0.5, 0.75, 1]
                      : undefined
                  }
                  tickFormatter={(value: number) =>
                    effectiveView === "traffic_share"
                      ? `${Math.round(value * 100)}%`
                      : formatCompactNumber(value, locale)
                  }
                  allowDecimals={false}
                  tickLine={false}
                  axisLine={false}
                  width={42}
                />
                <ChartTooltip
                  cursor={false}
                  itemSorter={(item) => -Number(item.value ?? 0)}
                  content={
                    <ChartTooltipContent
                      className="w-64 max-w-full gap-2 px-3 py-2.5 sm:w-72"
                      labelFormatter={(_, payload) => {
                        const bucket = payload[0]?.payload?.bucket;
                        return typeof bucket === "string"
                          ? formatTime.format(new Date(bucket))
                          : "";
                      }}
                      formatter={(value, name, item) => {
                        const attempts =
                          typeof value === "number" ? value : Number(value);
                        const total = Number(item.payload?.total ?? 0);
                        const series = model.meta.find(
                          (entry) => entry.key === name,
                        );
                        return (
                          <div className="flex w-full min-w-0 items-center gap-2">
                            <span
                              aria-hidden
                              className="size-2 shrink-0 rounded-sm"
                              style={{ backgroundColor: series?.color }}
                            />
                            <span className="min-w-0 flex-1 truncate font-medium text-ink-900">
                              {series?.label ?? name}
                            </span>
                            {series?.historical ? (
                              <Badge variant="neutral">{t("historical")}</Badge>
                            ) : null}
                            <span className="shrink-0 text-right tabular-nums text-ink-700">
                              {t("attempts", {
                                count: attempts.toLocaleString(locale),
                              })}
                              {total > 0
                                ? ` · ${new Intl.NumberFormat(locale, {
                                    style: "percent",
                                    maximumFractionDigits: 1,
                                  }).format(attempts / total)}`
                                : ""}
                            </span>
                          </div>
                        );
                      }}
                    />
                  }
                />
                {model.meta.map((item, index) => (
                  <Area
                    key={item.key}
                    type="monotone"
                    dataKey={item.key}
                    stackId="attempts"
                    stroke={item.color}
                    fill={`url(#${gradientId}-${item.key})`}
                    animationDuration={CHART_DRAW_MS}
                    animationEasing={CHART_DRAW_EASING}
                    animationBegin={index * CHART_SERIES_STAGGER_MS}
                  />
                ))}
              </AreaChart>
            </ChartContainer>
            <figcaption className="sr-only">
              {t("textAlternative", {
                total: totalAttempts,
                route: route.label,
                protocol: protocolLabel,
                strategy: strategyLabel,
              })}
              {model.meta.map((item) => (
                <span key={item.key}>
                  {item.historical
                    ? t("textAlternativeHistorical", {
                        endpoint: item.label,
                      })
                    : null}
                  {t("textAlternativeEndpoint", {
                    endpoint: item.label,
                    attempts: item.totalAttempts,
                    share:
                      totalAttempts > 0
                        ? item.totalAttempts / totalAttempts
                        : 0,
                  })}
                </span>
              ))}
            </figcaption>
          </figure>
        )}
      </CardContent>
    </Card>
  );
}
