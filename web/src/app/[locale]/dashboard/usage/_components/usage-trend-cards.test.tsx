import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  MethodTrendCard,
  NetworkTrendCard,
  OverallTrendCard,
} from "./usage-trend-cards";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

const {
  methodSeriesMock,
  networkSeriesMock,
  overallSeriesMock,
  trendChartCardMock,
  useUsageByMethodQueryMock,
  useUsageByNetworkQueryMock,
  useUsageSeriesQueryMock,
} = vi.hoisted(() => ({
  methodSeriesMock: vi.fn(() => []),
  networkSeriesMock: vi.fn(() => []),
  overallSeriesMock: vi.fn(() => []),
  trendChartCardMock: vi.fn((_props: Record<string, unknown>) => null),
  useUsageByMethodQueryMock: vi.fn(),
  useUsageByNetworkQueryMock: vi.fn(),
  useUsageSeriesQueryMock: vi.fn(),
}));

vi.mock("@/components/dashboard/usage-trend-chart", () => ({
  bytesFormat: {},
  cacheByMethodSeries: vi.fn(() => []),
  cacheSeries: vi.fn(() => []),
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

vi.mock("./usage-filter-bar", () => ({
  DEFAULT_USAGE_RANGE: "weekly",
  UsageFilterToolchain: () => null,
  UsageRangeSelect: () => null,
}));

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
        <OverallTrendCard />
        <MethodTrendCard />
        <NetworkTrendCard />
      </>,
    );

    expect(trendChartCardMock).toHaveBeenCalledTimes(3);
    expect(trendChartCardMock.mock.calls.map(([props]) => props.kind)).toEqual([
      "area",
      "area",
      "area",
    ]);
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
        action: null,
        range: "hourly",
        dataThrough: "2026-07-24T12:30:00Z",
        dataThroughLabel: "dataThrough",
      }),
    );
  });
});
