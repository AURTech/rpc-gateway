import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { RpcUsageRange, UsageParams } from "@/api/usage/client";
import { createTestQueryClient, renderWithQuery } from "@/test/query";

import { UsageContent } from "./usage-content";

const labels: Record<string, string> = {
  "filters.toolbarAriaLabel": "Usage defaults",
  "filters.allAppsLabel": "All apps",
  "filters.defaultsLabel": "Default chart filters",
  "filters.applyToAll": "Apply to all",
  "filters.refresh": "Refresh",
  "filters.chainLabel": "Chain",
  "filters.networkLabel": "Network",
  "filters.allChains": "All chains",
  "filters.allNetworks": "All networks",
  "filters.searchPlaceholder": "Search chain or network",
  "filters.searchAria": "Search chain or network",
  "filters.noNetworkMatches": "No networks match.",
  "filters.rangeAriaLabel": "Time range",
  "filters.ranges.hourly": "Hourly",
  "filters.ranges.daily": "Daily",
  "filters.ranges.weekly": "Weekly",
  "filters.ranges.monthly": "Monthly",
  "kpi.ariaLabel": "Usage summary",
  "kpi.totalCalls.label": "Total calls",
  "kpi.successRate.label": "Success rate",
  "kpi.cacheHit.label": "Cache acceleration rate",
  "kpi.latency.label": "Avg latency",
  "kpi.traffic.label": "Traffic",
  "kpi.error.title": "Couldn't load summary",
  "kpi.error.retry": "Retry",
  "overall.title": "Requests over time",
  "overall.subhead": "Successful vs. failed requests.",
  "overall.success": "Success",
  "overall.failure": "Failure",
  "overall.empty": "No request activity",
  "methods.title": "By method",
  "methods.subhead": "Total calls per RPC method.",
  "methods.empty": "No method activity",
  "network.title": "By network",
  "network.subhead": "Total calls per chain and network.",
  "network.empty": "No network activity",
  "cache.title": "Cache hit rate",
  "cache.subhead": "Share of cache-eligible requests served from cache.",
  "cache.label": "Hit rate",
  "cache.empty": "No cache-eligible requests",
  "cacheByMethod.title": "Cache hit rate by method",
  "cacheByMethod.subhead": "Compare cache hit rates by method.",
  "cacheByMethod.empty": "No cache-eligible method activity",
  "traffic.title": "Network traffic",
  "traffic.subhead": "Upload and download traffic trends.",
  "traffic.upload": "Upload",
  "traffic.download": "Download",
  "traffic.empty": "No traffic",
  "latency.title": "Average latency",
  "latency.subhead": "End-to-end request latency trends.",
  "latency.label": "Average latency",
  "latency.empty": "No latency data",
  "error.title": "Couldn't load usage",
  "error.retry": "Retry",
};

vi.mock("next-intl", () => ({
  useTranslations:
    (namespace: string) =>
    (key: string, values?: Record<string, string | number>) => {
      const scopedKey = namespace.endsWith(".kpi") ? `kpi.${key}` : key;
      let label = labels[scopedKey] ?? scopedKey;
      for (const [name, value] of Object.entries(values ?? {})) {
        label = label.replace(`{${name}}`, String(value));
      }
      return label;
    },
  useLocale: () => "en",
}));

const {
  useUsageSummaryQueryMock,
  useUsageSeriesQueryMock,
  useUsageByMethodQueryMock,
  useUsageByNetworkQueryMock,
} = vi.hoisted(() => ({
  useUsageSummaryQueryMock: vi.fn(),
  useUsageSeriesQueryMock: vi.fn(),
  useUsageByMethodQueryMock: vi.fn(),
  useUsageByNetworkQueryMock: vi.fn(),
}));

vi.mock("@/hooks/use-usage", () => ({
  usageKeys: { all: ["usage"] },
  useUsageSummaryQuery: useUsageSummaryQueryMock,
  useUsageSeriesQuery: useUsageSeriesQueryMock,
  useUsageByMethodQuery: useUsageByMethodQueryMock,
  useUsageByNetworkQuery: useUsageByNetworkQueryMock,
}));

function okQuery<T>(data: T) {
  return {
    data,
    isPending: false,
    isError: false,
    isFetching: false,
    refetch: vi.fn(),
  };
}

function emptySeries(params: { range?: RpcUsageRange }) {
  return okQuery({
    time_range: params.range ?? "weekly",
    data_through: "2026-01-08T00:00:00Z",
    items: [],
  });
}

// Zero-filled window: what the server actually returns for "no activity" —
// every bucket present, every counter zero.
function zeroFilledMethodSeries(params: { range?: RpcUsageRange }) {
  return okQuery({
    time_range: params.range ?? "weekly",
    granularity: "daily",
    data_through: "2026-01-08T00:00:00Z",
    items: [
      {
        method: "eth_call",
        points: [{ bucket_start: "2026-01-01T00:00:00Z", ...zeroMetrics() }],
      },
    ],
  });
}

function zeroMetrics() {
  return {
    total_requests: 0,
    successful_requests: 0,
    failed_requests: 0,
    success_rate: 0,
    total_duration_ms: 0,
    avg_duration_ms: 0,
    total_request_bytes: 0,
    total_response_bytes: 0,
    total_traffic_bytes: 0,
    cache_eligible_requests: 0,
    cache_hit_requests: 0,
    cache_hit_rate: 0,
  };
}

function lastSummaryParams(): UsageParams {
  const call = useUsageSummaryQueryMock.mock.calls.at(-1);
  expect(call).toBeDefined();
  return call?.[0] as UsageParams;
}

function hasCallWithChain(mock: ReturnType<typeof vi.fn>, chain: string) {
  return mock.mock.calls.some(([params]) => params?.chain === chain);
}

function hasCallWithScope(
  mock: ReturnType<typeof vi.fn>,
  scope: { chain: string; network: string },
) {
  return mock.mock.calls.some(
    ([params]) =>
      params?.chain === scope.chain && params?.network === scope.network,
  );
}

function hasCallWithRange(
  mock: ReturnType<typeof vi.fn>,
  range: RpcUsageRange,
) {
  return mock.mock.calls.some(([params]) => params?.range === range);
}

function renderUsage() {
  const user = userEvent.setup();
  const queryClient = createTestQueryClient();
  const invalidateQueries = vi.spyOn(queryClient, "invalidateQueries");
  const view = renderWithQuery(<UsageContent />, queryClient);
  const toolbar = screen.getByRole("toolbar", { name: "Usage defaults" });
  return { user, toolbar, invalidateQueries, ...view };
}

beforeEach(() => {
  vi.clearAllMocks();

  useUsageSummaryQueryMock.mockImplementation(() =>
    okQuery({
      ...zeroMetrics(),
      total_requests: 100,
      successful_requests: 95,
      failed_requests: 5,
      success_rate: 0.95,
      avg_duration_ms: 12.34,
      total_traffic_bytes: 3072,
      cache_hit_rate: 0.5,
      time_range: "weekly",
      start_at: "2026-07-17T00:00:00Z",
      end_at: "2026-07-24T00:00:00Z",
      data_through: "2026-07-24T00:00:00Z",
    }),
  );
  useUsageSeriesQueryMock.mockImplementation(emptySeries);
  useUsageByMethodQueryMock.mockImplementation(emptySeries);
  useUsageByNetworkQueryMock.mockImplementation(emptySeries);
});

describe("UsageContent filters", () => {
  it("renders every chart supported by the v2 usage APIs", () => {
    renderUsage();

    expect(screen.getByText("Cache hit rate")).toBeInTheDocument();
    expect(screen.getByText("Cache hit rate by method")).toBeInTheDocument();
    expect(screen.getByText("Network traffic")).toBeInTheDocument();
    expect(screen.getByText("Average latency")).toBeInTheDocument();
    expect(screen.queryByText("By gateway")).not.toBeInTheDocument();
    expect(useUsageSeriesQueryMock).toHaveBeenCalledWith({
      range: "weekly",
    });
    expect(useUsageSeriesQueryMock).toHaveBeenCalledTimes(2);
    expect(useUsageByNetworkQueryMock).toHaveBeenCalledWith({
      range: "weekly",
      limit: 100,
    });
    expect(useUsageByNetworkQueryMock).toHaveBeenCalledTimes(3);
    expect(useUsageByMethodQueryMock).toHaveBeenCalledWith({
      range: "weekly",
      rank_by: "cache_eligible_requests",
      limit: 8,
    });
  });

  it("renders KPI tiles from the v2 summary window", () => {
    renderUsage();

    expect(screen.getByText("Total calls")).toBeInTheDocument();
    expect(screen.getByText("100")).toBeInTheDocument();
    // Default page range drives the summary query.
    expect(lastSummaryParams()).toEqual({ range: "weekly" });
  });

  it("does not render charts without v2 API support", () => {
    renderUsage();

    expect(document.querySelectorAll("[data-slot='card']")).toHaveLength(7);
    expect(screen.queryByText("Upstream attempts")).not.toBeInTheDocument();
    expect(screen.queryByText("Upstream traffic")).not.toBeInTheDocument();
    expect(screen.queryByText("Upstream latency")).not.toBeInTheDocument();
  });

  it("keeps chart filters unchanged until global defaults are applied", async () => {
    const { user, toolbar } = renderUsage();

    await user.click(
      within(toolbar).getByRole("button", { name: "Chain / Network" }),
    );
    await user.click(
      await screen.findByRole("menuitemradio", { name: "Ethereum · Mainnet" }),
    );

    // The global toolbar scope does not reach the charts until "Apply to all".
    expect(hasCallWithChain(useUsageByMethodQueryMock, "ethereum")).toBe(false);
    expect(lastSummaryParams()).toEqual({
      range: "weekly",
      chain: "ethereum",
      network: "mainnet",
    });

    await user.click(
      within(toolbar).getByRole("button", { name: "Apply to all" }),
    );

    await waitFor(() => {
      expect(
        hasCallWithScope(useUsageByMethodQueryMock, {
          chain: "ethereum",
          network: "mainnet",
        }),
      ).toBe(true);
      expect(
        hasCallWithScope(useUsageSeriesQueryMock, {
          chain: "ethereum",
          network: "mainnet",
        }),
      ).toBe(true);
    });
  });

  it("changes one chart filter without changing sibling charts", async () => {
    const { user } = renderUsage();
    const methodCard = screen
      .getByText("By method")
      .closest("[data-slot='card']");
    expect(methodCard).not.toBeNull();

    await user.click(
      within(methodCard as HTMLElement).getByRole("button", {
        name: "Chain / Network",
      }),
    );
    await user.type(
      await screen.findByRole("searchbox", {
        name: "Search chain or network",
      }),
      "base",
    );
    await user.click(
      await screen.findByRole("menuitemradio", { name: "Base · Mainnet" }),
    );

    await waitFor(() => {
      expect(
        hasCallWithScope(useUsageByMethodQueryMock, {
          chain: "base",
          network: "mainnet",
        }),
      ).toBe(true);
    });
    expect(
      hasCallWithScope(useUsageByNetworkQueryMock, {
        chain: "base",
        network: "mainnet",
      }),
    ).toBe(false);

    await user.click(
      within(methodCard as HTMLElement).getByRole("button", {
        name: "Time range",
      }),
    );
    await user.click(
      await screen.findByRole("menuitemradio", { name: "Hourly" }),
    );

    await waitFor(() => {
      expect(hasCallWithRange(useUsageByMethodQueryMock, "hourly")).toBe(true);
    });
    expect(hasCallWithRange(useUsageByNetworkQueryMock, "hourly")).toBe(false);
  });

  it("uses the global range for the KPI summary window", async () => {
    const { user, toolbar } = renderUsage();

    expect(lastSummaryParams()).toEqual({ range: "weekly" });

    await user.click(within(toolbar).getByRole("radio", { name: "Hourly" }));
    await waitFor(() => {
      expect(lastSummaryParams()).toEqual({ range: "hourly" });
    });
  });

  it("refreshes usage data without resetting filters", async () => {
    const { user, toolbar, invalidateQueries } = renderUsage();

    await user.click(
      within(toolbar).getByRole("button", { name: "Chain / Network" }),
    );
    await user.click(
      await screen.findByRole("menuitemradio", { name: "Ethereum · Mainnet" }),
    );
    await user.click(within(toolbar).getByRole("radio", { name: "Daily" }));
    await user.click(
      within(toolbar).getByRole("button", { name: "Apply to all" }),
    );

    await waitFor(() => {
      expect(lastSummaryParams()).toEqual({
        range: "daily",
        chain: "ethereum",
        network: "mainnet",
      });
      expect(hasCallWithRange(useUsageByMethodQueryMock, "daily")).toBe(true);
    });

    await user.click(within(toolbar).getByRole("button", { name: "Refresh" }));

    await waitFor(() => {
      expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["usage"] });
    });
    expect(lastSummaryParams()).toEqual({
      range: "daily",
      chain: "ethereum",
      network: "mainnet",
    });
    expect(within(toolbar).getByRole("radio", { name: "Daily" })).toBeChecked();
  });

  it("shows the empty state for a zero-filled window instead of a chart", async () => {
    useUsageByMethodQueryMock.mockImplementation(zeroFilledMethodSeries);

    renderUsage();

    expect(await screen.findByText("No method activity")).toBeInTheDocument();
  });
});
