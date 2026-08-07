import { describe, expect, it } from "vitest";

import { okResponse, stubFetch } from "@/test/fetch";

import {
  getUsageByMethod,
  getUsageByNetwork,
  getUsageSeries,
  getUsageSummary,
} from "./client";

const fetchMock = stubFetch();

const metrics = {
  total_requests: 10,
  successful_requests: 8,
  failed_requests: 2,
  success_rate: 0.8,
  total_duration_ms: 500,
  avg_duration_ms: 50,
  total_request_bytes: 100,
  total_response_bytes: 200,
  total_traffic_bytes: 300,
  cache_eligible_requests: 6,
  cache_hit_requests: 3,
  cache_hit_rate: 0.5,
};

describe("usage api client", () => {
  it("maps summary filters to the v2 query contract", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        ...metrics,
        time_range: "weekly",
        start_at: "2026-07-17T00:00:00Z",
        end_at: "2026-07-24T00:00:00Z",
        data_through: "2026-07-24T00:00:00Z",
      }),
    );

    const result = await getUsageSummary({
      range: "weekly",
      app_id: "app_1",
      chain: "ethereum",
      network: "mainnet",
    });

    expect(result.success_rate).toBe(0.8);
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toMatch(/\/v2\/usage\/summary\?/);
    expect(url).toMatch(/time_range=weekly/);
    expect(url).toMatch(/app_id=app_1/);
    expect(url).toMatch(/chain=ethereum/);
    expect(url).toMatch(/network=mainnet/);
  });

  it("parses the shared full-metric v2 series", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        time_range: "hourly",
        granularity: "five_minute",
        data_through: "2026-07-24T00:00:00Z",
        items: [{ ...metrics, bucket_start: "2026-07-24T00:00:00Z" }],
      }),
    );

    const result = await getUsageSeries({
      range: "hourly",
      gateway_id: "gateway_1",
    });

    expect(result.items[0].avg_duration_ms).toBe(50);
    expect(result.granularity).toBe("five_minute");
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/v2\/usage\/series\?/);
    expect(fetchMock.mock.calls[0][0]).toMatch(/time_range=hourly/);
  });

  it("sends method rank and parses the narrow method projection", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        time_range: "monthly",
        granularity: "daily",
        data_through: "2026-07-24T00:00:00Z",
        items: [
          {
            method: "eth_call",
            points: [
              {
                bucket_start: "2026-07-24T00:00:00Z",
                total_requests: 10,
                cache_eligible_requests: 8,
                cache_hit_requests: 6,
                cache_hit_rate: 0.75,
              },
            ],
          },
        ],
      }),
    );

    const result = await getUsageByMethod({
      range: "monthly",
      rank_by: "cache_eligible_requests",
      limit: 8,
    });

    expect(result.items[0].points[0].cache_hit_rate).toBe(0.75);
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toMatch(/\/v2\/usage\/methods\?/);
    expect(url).toMatch(/rank_by=cache_eligible_requests/);
    expect(url).toMatch(/limit=8/);
  });

  it("parses the network metric projection", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        time_range: "daily",
        granularity: "hourly",
        data_through: "2026-07-24T00:00:00Z",
        items: [
          {
            chain: "ethereum",
            chain_label: "Ethereum",
            network: "mainnet",
            network_label: "Mainnet",
            points: [
              {
                bucket_start: "2026-07-24T00:00:00Z",
                total_requests: 10,
                total_duration_ms: 125,
                avg_duration_ms: 12.5,
                cache_eligible_requests: 8,
                cache_hit_requests: 6,
                cache_hit_rate: 0.75,
              },
            ],
          },
        ],
      }),
    );

    const result = await getUsageByNetwork({ range: "daily", limit: 10 });

    expect(result.items[0].points[0].total_requests).toBe(10);
    expect(result.items[0].points[0].avg_duration_ms).toBe(12.5);
    expect(result.items[0].points[0].cache_hit_rate).toBe(0.75);
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/v2\/usage\/networks\?/);
  });
});
