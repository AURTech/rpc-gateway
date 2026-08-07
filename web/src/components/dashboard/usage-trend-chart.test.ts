import { describe, expect, it } from "vitest";

import type {
  RpcUsageByMethod,
  RpcUsageByNetwork,
  RpcUsageMetricsPoint,
  RpcUsageSeries,
} from "@/api/usage/client";

import {
  bytesFormat,
  cacheByMethodSeries,
  cacheSeries,
  durationAxis,
  durationFormat,
  formatCompactNumber,
  hasSingleBucket,
  latencySeries,
  methodSeries,
  networkSeries,
  overallSeries,
  percentAxis,
  percentFormat,
  splitDuration,
  trafficSeries,
} from "./usage-trend-chart";

function metricsPoint(
  bucket_start: string,
  overrides: Partial<RpcUsageMetricsPoint>,
): RpcUsageMetricsPoint {
  return {
    bucket_start,
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
    ...overrides,
  };
}

function usageSeries(items: RpcUsageMetricsPoint[]): RpcUsageSeries {
  return {
    time_range: "weekly",
    granularity: "daily",
    data_through: "2026-01-08T00:00:00Z",
    items,
  };
}

function methodUsage(items: RpcUsageByMethod["items"]): RpcUsageByMethod {
  return {
    time_range: "weekly",
    granularity: "daily",
    data_through: "2026-01-08T00:00:00Z",
    items,
  };
}

function networkUsage(items: RpcUsageByNetwork["items"]): RpcUsageByNetwork {
  return {
    time_range: "weekly",
    granularity: "daily",
    data_through: "2026-01-08T00:00:00Z",
    items,
  };
}

type NetworkPoint = RpcUsageByNetwork["items"][number]["points"][number];

function networkPoint(
  bucket_start: string,
  overrides: Partial<NetworkPoint>,
): NetworkPoint {
  return {
    bucket_start,
    total_requests: 0,
    total_duration_ms: 0,
    avg_duration_ms: 0,
    cache_eligible_requests: 0,
    cache_hit_requests: 0,
    cache_hit_rate: 0,
    ...overrides,
  };
}

describe("usage series adapters", () => {
  it("splits successful and failed requests into semantic bands", () => {
    const result = overallSeries(
      usageSeries([
        metricsPoint("2026-01-01T00:00:00Z", {
          total_requests: 10,
          successful_requests: 8,
          failed_requests: 2,
        }),
      ]),
      { success: "Success", failure: "Failure" },
    );

    expect(result.map((item) => item.key)).toEqual(["success", "failure"]);
    expect(result.map((item) => item.points[0].value)).toEqual([8, 2]);
    expect(result.map((item) => item.color)).toEqual([
      "var(--positive)",
      "var(--danger)",
    ]);
  });

  it("maps cache hit rate into independent network lines", () => {
    const result = cacheSeries(
      networkUsage([
        {
          chain: "ethereum",
          chain_label: "Ethereum",
          network: "mainnet",
          network_label: "Mainnet",
          points: [
            networkPoint("2026-01-01T00:00:00Z", {
              cache_eligible_requests: 10,
              cache_hit_rate: 0,
            }),
          ],
        },
        {
          chain: "polygon",
          chain_label: "Polygon",
          network: "mainnet",
          network_label: "Mainnet",
          points: [
            networkPoint("2026-01-01T00:00:00Z", {
              cache_eligible_requests: 4,
              cache_hit_requests: 2,
              cache_hit_rate: 0.5,
            }),
          ],
        },
        {
          chain: "base",
          chain_label: "Base",
          network: "mainnet",
          network_label: "Mainnet",
          points: [networkPoint("2026-01-01T00:00:00Z", {})],
        },
      ]),
    );

    expect(result.map((item) => item.label)).toEqual([
      "Ethereum · Mainnet",
      "Polygon · Mainnet",
    ]);
    expect(result.map((item) => item.points[0].value)).toEqual([0, 0.5]);
  });

  it("maps request and response traffic from the shared v2 series", () => {
    const result = trafficSeries(
      usageSeries([
        metricsPoint("2026-01-01T00:00:00Z", {
          total_request_bytes: 12,
          total_response_bytes: 34,
          total_traffic_bytes: 46,
        }),
      ]),
      { request: "Upload", response: "Download" },
    );

    expect(result.map((item) => item.points[0].value)).toEqual([12, 34]);
  });

  it("maps average request latency into independent network lines", () => {
    const result = latencySeries(
      networkUsage([
        {
          chain: "ethereum",
          chain_label: "Ethereum",
          network: "mainnet",
          network_label: "Mainnet",
          points: [
            networkPoint("2026-01-01T00:00:00Z", {
              total_requests: 2,
              avg_duration_ms: 12.5,
            }),
          ],
        },
        {
          chain: "polygon",
          chain_label: "Polygon",
          network: "mainnet",
          network_label: "Mainnet",
          points: [
            networkPoint("2026-01-01T00:00:00Z", {
              total_requests: 4,
              avg_duration_ms: 20,
            }),
          ],
        },
      ]),
    );

    expect(result.map((item) => item.label)).toEqual([
      "Ethereum · Mainnet",
      "Polygon · Mainnet",
    ]);
    expect(result.map((item) => item.points[0].value)).toEqual([12.5, 20]);
    expect(durationFormat.format(12.5, false)).toBe("12.5 ms");
  });

  it("collapses zero-filled aggregate series to empty charts", () => {
    const data = usageSeries([metricsPoint("2026-01-01T00:00:00Z", {})]);

    expect(
      overallSeries(data, { success: "Success", failure: "Failure" }),
    ).toEqual([]);
    expect(
      trafficSeries(data, { request: "Request", response: "Response" }),
    ).toEqual([]);
  });

  it("collapses network series without relevant samples", () => {
    const data = networkUsage([
      {
        chain: "ethereum",
        chain_label: "Ethereum",
        network: "mainnet",
        network_label: "Mainnet",
        points: [networkPoint("2026-01-01T00:00:00Z", {})],
      },
    ]);

    expect(cacheSeries(data)).toEqual([]);
    expect(latencySeries(data)).toEqual([]);
  });
});

describe("breakdown adapters", () => {
  it("maps the narrow request-by-method projection", () => {
    const data = methodUsage([
      {
        method: "eth_call",
        points: [
          {
            bucket_start: "2026-01-01T00:00:00Z",
            total_requests: 5,
            cache_eligible_requests: 4,
            cache_hit_requests: 3,
            cache_hit_rate: 0.75,
          },
        ],
      },
    ]);

    expect(methodSeries(data)[0].points[0].value).toBe(5);
    expect(cacheByMethodSeries(data)[0].points[0].value).toBe(0.75);
  });

  it("keeps equal network names separate across chains", () => {
    const point = networkPoint("2026-01-01T00:00:00Z", {
      total_requests: 5,
    });
    const result = networkSeries(
      networkUsage([
        {
          chain: "ethereum",
          chain_label: "Ethereum",
          network: "mainnet",
          network_label: "Mainnet",
          points: [point],
        },
        {
          chain: "polygon",
          chain_label: "Polygon",
          network: "mainnet",
          network_label: "Mainnet",
          points: [point],
        },
      ]),
    );

    expect(result.map((item) => item.key)).toEqual([
      "ethereum_mainnet",
      "polygon_mainnet",
    ]);
  });
});

describe("duration units", () => {
  it("switches from milliseconds to seconds at one second", () => {
    expect(splitDuration(999.9)).toEqual({ value: 999.9, unit: "ms" });
    expect(splitDuration(1000)).toEqual({ value: 1, unit: "s" });
    expect(splitDuration(2500)).toEqual({ value: 2.5, unit: "s" });
  });

  it("never labels a value above a second in milliseconds", () => {
    expect(durationFormat.format(12.5, false)).toBe("12.5 ms");
    expect(durationFormat.format(999, false)).toBe("999 ms");
    expect(durationFormat.format(1234.5, false)).toBe("1.23 s");
    expect(durationFormat.format(1234.5, true)).toBe("1.2 s");
    expect(durationFormat.format(90_000, false)).toBe("90 s");
  });

  it("keeps one unit across the whole axis", () => {
    const sub = durationAxis(420);
    expect(sub.ticks.map((v) => sub.tickFormat?.(v))).toEqual([
      "0 ms",
      "100 ms",
      "200 ms",
      "300 ms",
      "400 ms",
      "500 ms",
    ]);

    // The peak alone would read as milliseconds; the ceiling is what decides.
    const spanning = durationAxis(900);
    expect(spanning.top).toBe(1000);
    expect(spanning.ticks.map((v) => spanning.tickFormat?.(v))).toEqual([
      "0.0 s",
      "0.2 s",
      "0.4 s",
      "0.6 s",
      "0.8 s",
      "1.0 s",
    ]);
  });

  it("gives ticks only the digits their step needs", () => {
    const whole = durationAxis(9_000);
    expect(whole.ticks.map((v) => whole.tickFormat?.(v))).toEqual([
      "0 s",
      "2 s",
      "4 s",
      "6 s",
      "8 s",
      "10 s",
    ]);

    const fractional = durationAxis(2_200);
    expect(fractional.ticks.map((v) => fractional.tickFormat?.(v))).toEqual([
      "0.0 s",
      "0.5 s",
      "1.0 s",
      "1.5 s",
      "2.0 s",
      "2.5 s",
    ]);
  });
});

describe("percentAxis", () => {
  it("fits the ceiling to the observed peak instead of pinning 100%", () => {
    expect(percentAxis(0.03)).toMatchObject({
      top: 0.03,
      ticks: [0, 0.01, 0.02, 0.03],
    });
    expect(percentAxis(0.42)).toMatchObject({
      top: 0.5,
      ticks: [0, 0.25, 0.5],
    });
  });

  it("keeps the full scale when the peak reaches it", () => {
    expect(percentAxis(1)).toMatchObject({
      top: 1,
      ticks: [0, 0.25, 0.5, 0.75, 1],
    });
    expect(percentAxis(0.98)).toMatchObject({
      top: 1,
      ticks: [0, 0.25, 0.5, 0.75, 1],
    });
  });

  it("never exceeds 100% and never dips below the baseline", () => {
    expect(percentAxis(1.4).top).toBe(1);
    expect(percentAxis(0.004).ticks[0]).toBe(0);
  });

  it("falls back to the full scale when nothing was measured", () => {
    expect(percentAxis(0)).toMatchObject({
      top: 1,
      ticks: [0, 0.25, 0.5, 0.75, 1],
    });
  });

  it("gives axis ticks enough digits to stay distinct", () => {
    const coarse = percentAxis(0.42);
    expect(coarse.ticks.map((v) => coarse.tickFormat?.(v))).toEqual([
      "0%",
      "25%",
      "50%",
    ]);

    const fine = percentAxis(0.004);
    expect(fine.ticks.map((v) => fine.tickFormat?.(v))).toEqual([
      "0.0%",
      "0.1%",
      "0.2%",
      "0.3%",
      "0.4%",
    ]);
  });
});

describe("percentFormat", () => {
  it("adds a digit to tooltip values under one percent", () => {
    expect(percentFormat.format(0.4237, false)).toBe("42.4%");
    expect(percentFormat.format(0.0042, false)).toBe("0.42%");
    expect(percentFormat.format(0, false)).toBe("0.0%");
  });
});

describe("bytesFormat", () => {
  it("keeps byte axis labels wide enough to avoid wrapping", () => {
    expect(bytesFormat.axisWidth).toBe(80);
  });
});

describe("formatCompactNumber", () => {
  it("keeps small values unchanged and abbreviates thousands", () => {
    expect(formatCompactNumber(999, "en")).toBe("999");
    expect(formatCompactNumber(1_000, "en")).toBe("1k");
    expect(formatCompactNumber(10_000, "en")).toBe("10k");
    expect(formatCompactNumber(12_500, "en")).toBe("12.5k");
  });

  it("scales larger values and promotes rounded boundaries", () => {
    expect(formatCompactNumber(1_000_000, "en")).toBe("1m");
    expect(formatCompactNumber(1_250_000_000, "en")).toBe("1.3b");
    expect(formatCompactNumber(999_999, "en")).toBe("1m");
    expect(formatCompactNumber(1_000_000_000_000, "en")).toBe("1t");
  });
});

describe("single-bucket charts", () => {
  it("shows point markers only when a range has one bucket", () => {
    expect(hasSingleBucket(1)).toBe(true);
    expect(hasSingleBucket(12)).toBe(false);
    expect(hasSingleBucket(24)).toBe(false);
  });
});
