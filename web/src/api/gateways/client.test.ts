import { describe, expect, it } from "vitest";

import { okResponse, stubFetch } from "@/test/fetch";

import { bulkUpdateGateways } from "./client";

const fetchMock = stubFetch();

const gateway = {
  id: "gateway-1",
  app_id: "app-1",
  app_name: "production",
  name: "ethereum-mainnet",
  chain: "ethereum",
  network: "mainnet",
  enabled: false,
  effective_enabled: false,
  version: 2,
  access_points: [
    { transport: "jsonrpc", url: "https://rpc.example.test/{path_key}" },
  ],
  created_at: "2026-01-01T00:00:00Z",
  modified_at: "2026-01-02T00:00:00Z",
};

describe("V2 gateway client", () => {
  it("sends one collection PATCH and parses all updated gateways", async () => {
    fetchMock.mockResolvedValueOnce(okResponse({ total: 1, items: [gateway] }));
    const input = {
      enabled: false,
      gateways: [{ id: "gateway-1", expected_version: 1 }],
    };

    const result = await bulkUpdateGateways("app-1", input);

    expect(result).toEqual({ total: 1, items: [gateway] });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/v2\/apps\/app-1\/gateways$/);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: "PATCH",
      body: JSON.stringify(input),
    });
  });
});
