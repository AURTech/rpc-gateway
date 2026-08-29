import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  CachePerformanceCard,
  MethodTrendCard,
  NetworkTrendCard,
  OverallTrendCard,
} from "./usage-trend-cards";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

const {
  cacheByMethodSeriesMock,
  cacheSeriesMock,
  methodSeriesMock,
  networkSeriesMock,
  overallSeriesMock,
  trendChartCardMock,
  useUsageByMethodQueryMock,
  useUsageByNetworkQueryMock,
  useUsageSeriesQueryMock,
} = vi.hoisted(() => ({
  cacheByMethodSeriesMock: vi.fn(() => []),
  cacheSeriesMock: vi.fn(() => []),
  methodSeriesMock: vi.fn(() => []),
  networkSeriesMock: vi.fn(() => []),
  overallSeriesMock: vi.fn(() => []),
  trendChartCardMock: vi.fn(
    (_props: Record<string, unknown>): ReactNode => null,
  ),
  useUsageByMethodQueryMock: vi.fn(),
  useUsageByNetworkQueryMock: vi.fn(),
  useUsageSeriesQueryMock: vi.fn(),
}));

vi.mock("@/components/dashboard/usage-trend-chart", () => ({
  bytesFormat: {},
  cacheByMethodSeries: cacheByMethodSeriesMock,
  cacheSeries: cacheSeriesMock,
  durationFormat: {},
  latencySeries: vi.fn(() => []),
  methodSeries: methodSeriesMock,
  networkSeries: networkSeriesMock,
  overallSeries: overallSeriesMock,
  percentFormat: {},
  trafficSeries: vi.fn(() => []),
  TrendChartCard: trendChartCardMock,
}));

vi.mock("@/hooks/use-usage", () => ({
  useUsageByMethodQuery: useUsageByMethodQueryMock,
  useUsageByNetworkQuery: useUsageByNetworkQueryMock,
  useUsageSeriesQuery: useUsageSeriesQueryMock,
}));

const FILTERS = { range: "weekly" } as const;

const QUERY = {
  data: undefined,
  isPending: false,
  isFetching: false,
  isError: false,
  refetch: vi.fn(),
};

describe("request volume trend cards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useUsageByMethodQueryMock.mockReturnValue(QUERY);
    useUsageByNetworkQueryMock.mockReturnValue(QUERY);
    useUsageSeriesQueryMock.mockReturnValue(QUERY);
  });

  it("plots overall, method, and network values on a shared unstacked axis", () => {
    render(
      <>
        <OverallTrendCard filters={FILTERS} />
        <MethodTrendCard filters={FILTERS} />
        <NetworkTrendCard filters={FILTERS} />
      </>,
    );

    expect(trendChartCardMock).toHaveBeenCalledTimes(3);
    expect(trendChartCardMock.mock.calls.map(([props]) => props.kind)).toEqual([
      "area",
      "area",
      "area",
    ]);
  });

  it("keeps cache hit rate in one card and swaps the series per view", async () => {
    const user = userEvent.setup();
    trendChartCardMock.mockImplementation((props) => props.action as ReactNode);
    cacheSeriesMock.mockReturnValue([]);
    cacheByMethodSeriesMock.mockReturnValue([]);
    render(<CachePerformanceCard filters={FILTERS} />);

    expect(useUsageByNetworkQueryMock).toHaveBeenCalledWith({
      range: "weekly",
      limit: 100,
    });
    expect(useUsageByMethodQueryMock).toHaveBeenCalledWith({
      range: "weekly",
      rank_by: "cache_eligible_requests",
      limit: 8,
    });
    expect(trendChartCardMock).toHaveBeenCalledTimes(1);
    expect(trendChartCardMock.mock.lastCall?.[0]).toEqual(
      expect.objectContaining({
        title: "cache.title",
        subhead: "cache.subhead",
        emptyLabel: "cache.empty",
        kind: "line",
      }),
    );
    expect(cacheSeriesMock).toHaveBeenCalled();
    expect(cacheByMethodSeriesMock).not.toHaveBeenCalled();

    await user.click(screen.getByRole("radio", { name: "cache.views.method" }));

    expect(trendChartCardMock.mock.lastCall?.[0]).toEqual(
      expect.objectContaining({
        title: "cache.title",
        subhead: "cacheByMethod.subhead",
        emptyLabel: "cacheByMethod.empty",
      }),
    );
    expect(cacheByMethodSeriesMock).toHaveBeenCalled();
  });

  it("uses parent-owned filters without rendering a per-card action", () => {
    useUsageSeriesQueryMock.mockReturnValue({
      ...QUERY,
      data: {
        time_range: "hourly",
        granularity: "five_minute",
        data_through: "2026-07-24T12:30:00Z",
        items: [],
      },
    });
    render(<OverallTrendCard filters={{ range: "hourly" }} />);

    expect(useUsageSeriesQueryMock).toHaveBeenCalledWith({ range: "hourly" });
    expect(trendChartCardMock.mock.lastCall?.[0]).toEqual(
      expect.objectContaining({
        range: "hourly",
        dataThrough: "2026-07-24T12:30:00Z",
        dataThroughLabel: "dataThrough",
      }),
    );
  });
});
