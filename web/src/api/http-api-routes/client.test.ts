import { describe, expect, it } from "vitest";

import { okResponse, stubFetch } from "@/test/fetch";

import { getHttpApiRoute, putHttpApiRoute } from "./client";

const fetchMock = stubFetch();

const route = {
  id: "http-route-1",
  gateway_id: "gateway-1",
  max_attempts: 3,
  retry_policy: "safe_only",
  strategy: {
    type: "priority_failover",
    targets: [{ endpoint_id: "endpoint-1", position: 0 }],
  },
  version: 2,
  created_at: "2026-01-01T00:00:00Z",
  modified_at: "2026-01-02T00:00:00Z",
};

describe("HTTP API route client", () => {
  it("gets and parses a gateway HTTP API route", async () => {
    fetchMock.mockResolvedValueOnce(okResponse(route));

    await expect(getHttpApiRoute("gateway-1")).resolves.toEqual(route);
    expect(fetchMock.mock.calls[0][0]).toMatch(
      /\/v2\/gateways\/gateway-1\/http-api-route$/,
    );
  });

  it("replaces a route with the supplied optimistic version", async () => {
    fetchMock.mockResolvedValueOnce(okResponse(route));
    const input = {
      expected_version: 1,
      max_attempts: 3,
      retry_policy: "safe_only" as const,
      strategy: {
        type: "priority_failover" as const,
        targets: [{ endpoint_id: "endpoint-1" }],
      },
    };

    await putHttpApiRoute("gateway-1", input);

    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: "PUT",
      body: JSON.stringify(input),
    });
  });
});
