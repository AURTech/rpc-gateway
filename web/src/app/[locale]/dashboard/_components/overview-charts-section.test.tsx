import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OverviewChartsSection } from "./overview-charts-section";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

const {
  overallSeriesMock,
  refetchMock,
  trafficSeriesMock,
  trendChartCardMock,
  useUsageSeriesQueryMock,
} = vi.hoisted(() => ({
  overallSeriesMock: vi.fn(() => [{ key: "calls" }]),
  refetchMock: vi.fn(),
  trafficSeriesMock: vi.fn(() => [{ key: "traffic" }]),
  trendChartCardMock: vi.fn((_props: Record<string, unknown>) => null),
  useUsageSeriesQueryMock: vi.fn(),
}));

vi.mock("@/components/dashboard/usage-trend-chart", () => ({
  bytesFormat: {},
  overallSeries: overallSeriesMock,
  trafficSeries: trafficSeriesMock,
  TrendChartCard: trendChartCardMock,
}));

vi.mock("@/hooks/use-usage", () => ({
  useUsageSeriesQuery: useUsageSeriesQueryMock,
}));

describe("OverviewChartsSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useUsageSeriesQueryMock.mockReturnValue({
      data: {
        time_range: "weekly",
        granularity: "daily",
        data_through: "2026-07-24T00:00:00Z",
        items: [],
      },
      isPending: true,
      isError: true,
      refetch: refetchMock,
    });
  });

  it("drives both charts from one v2 series query", () => {
    render(<OverviewChartsSection />);

    expect(useUsageSeriesQueryMock).toHaveBeenCalledWith({
      range: "weekly",
    });

    const data = useUsageSeriesQueryMock.mock.results[0].value.data;
    expect(overallSeriesMock).toHaveBeenCalledWith(data, {
      success: "calls.success",
      failure: "calls.failure",
    });
    expect(trafficSeriesMock).toHaveBeenCalledWith(data, {
      request: "traffic.upload",
      response: "traffic.download",
    });
    expect(trendChartCardMock).toHaveBeenCalledTimes(2);

    const cardProps = trendChartCardMock.mock.calls.map(([props]) => props);
    expect(cardProps.every((props) => props.isPending === true)).toBe(true);
    expect(cardProps.every((props) => props.isError === true)).toBe(true);
    expect(
      cardProps.every((props) => props.dataThrough === "2026-07-24T00:00:00Z"),
    ).toBe(true);
    expect(
      cardProps.every((props) => props.dataThroughLabel === "dataThrough"),
    ).toBe(true);
    for (const props of cardProps) {
      (props.onRetry as () => void)();
    }
    expect(refetchMock).toHaveBeenCalledTimes(2);
  });

  it("forwards the app scope into the series query", () => {
    render(<OverviewChartsSection appId="app_1" />);

    expect(useUsageSeriesQueryMock).toHaveBeenCalledWith({
      range: "weekly",
      app_id: "app_1",
    });
  });

  it("updates the shared query range", async () => {
    const user = userEvent.setup();
    render(<OverviewChartsSection />);

    await user.click(screen.getByRole("radio", { name: "ranges.hourly" }));

    await waitFor(() => {
      expect(useUsageSeriesQueryMock).toHaveBeenLastCalledWith({
        range: "hourly",
      });
    });
  });
});
