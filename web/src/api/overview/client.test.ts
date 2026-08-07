import { describe, expect, it } from "vitest";

import { jsonResponse, stubFetch } from "@/test/fetch";

import { getOverview } from "./client";

const fetchMock = stubFetch();

describe("overview api client", () => {
  it("parses the fleet totals envelope", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        msg: "ok",
        data: {
          endpoint_total: 2,
          active_endpoint_total: 1,
          provider_total: 3,
          app_total: 4,
        },
      }),
    );

    const result = await getOverview();

    expect(result.endpoint_total).toBe(2);
    expect(result.active_endpoint_total).toBe(1);
    expect(result.provider_total).toBe(3);
    expect(result.app_total).toBe(4);
  });

  it("requests the v2 overview route", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        msg: "ok",
        data: {
          endpoint_total: 0,
          active_endpoint_total: 0,
          provider_total: 0,
          app_total: 0,
        },
      }),
    );

    await getOverview();

    expect(fetchMock.mock.calls[0][0] as string).toMatch(/\/v2\/overview$/);
  });
});
