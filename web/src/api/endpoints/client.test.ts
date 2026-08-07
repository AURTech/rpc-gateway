import { describe, expect, it } from "vitest";

import { okResponse, stubFetch } from "@/test/fetch";

import { bulkDeleteEndpoints, getEndpoint, listEndpoints } from "./client";

const fetchMock = stubFetch();

const endpoint = {
  id: "endpoint-1",
  account_id: "account-1",
  name: "primary",
  origin_type: "manual",
  provider: null,
  provider_external_id: null,
  provider_sync_status: null,
  provider_last_seen_at: null,
  chain: "ethereum",
  network: "mainnet",
  protocol: "jsonrpc",
  url: "https://rpc.example.com",
  enabled: true,
  auth: { type: "bearer", has_secret: true },
  version: 1,
  created_at: "2026-06-01T00:00:00Z",
  modified_at: "2026-06-01T00:00:00Z",
};

describe("V2 endpoint client", () => {
  it("keeps list authentication metadata secret-free", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        page: 1,
        size: 20,
        total: 1,
        max_page: 1,
        items: [endpoint],
      }),
    );

    const result = await listEndpoints();

    expect(result.items[0].auth).toEqual({
      type: "bearer",
      has_secret: true,
    });
  });

  it("parses the directly visible detail credential and configured URL", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        ...endpoint,
        configured_url: "https://rpc.example.com",
        auth: {
          type: "bearer",
          has_secret: true,
          secret: "bearer-secret",
        },
      }),
    );

    const detail = await getEndpoint("endpoint-1");

    expect(detail.configured_url).toBe("https://rpc.example.com");
    expect(detail.auth).toMatchObject({ secret: "bearer-secret" });
    expect(fetchMock.mock.calls[0][1]?.cache).toBe("no-store");
  });

  it("bulk-deletes endpoints and preserves referenced ids", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        total: 2,
        deleted: [{ id: "endpoint-1", version: 2, deleted: true }],
        referenced_ids: ["endpoint-2"],
      }),
    );

    const result = await bulkDeleteEndpoints(["endpoint-1", "endpoint-2"]);

    expect(result.referenced_ids).toEqual(["endpoint-2"]);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/v2/endpoints/bulk-delete"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          endpoint_ids: ["endpoint-1", "endpoint-2"],
        }),
      }),
    );
  });
});
