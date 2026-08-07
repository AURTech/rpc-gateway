import { describe, expect, it } from "vitest";

import { okResponse, stubFetch } from "@/test/fetch";

import { listAppKeys, setAppProvider } from "./client";

const fetchMock = stubFetch();

describe("V2 app key client", () => {
  it("parses directly visible keys without caching the response", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        total: 1,
        items: [
          {
            id: "key-1",
            api_key: "ak_visible",
            state: "revoked",
            expires_at: null,
            revoked_at: "2026-07-01T00:00:00Z",
            created_at: "2026-06-01T00:00:00Z",
          },
        ],
      }),
    );

    const keys = await listAppKeys("app-1");

    expect(keys.items[0]).toMatchObject({
      api_key: "ak_visible",
      state: "revoked",
    });
    expect(fetchMock.mock.calls[0][1]?.cache).toBe("no-store");
  });
});

describe("V2 app Provider client", () => {
  it("associates a Provider and parses Route Target statistics", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        app_id: "app-1",
        provider: {
          id: "provider-1",
          name: "Alchemy production",
          vendor: "alchemy",
          vendor_label: "Alchemy",
        },
        route_targets_added: 2,
        route_targets_removed: 0,
        route_targets_skipped: 0,
      }),
    );

    const result = await setAppProvider("app-1", "provider-1");

    expect(result.route_targets_added).toBe(2);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/v2/apps/app-1/provider"),
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ provider_id: "provider-1" }),
      }),
    );
  });
});
