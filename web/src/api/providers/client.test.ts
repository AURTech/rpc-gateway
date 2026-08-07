import { describe, expect, it } from "vitest";

import { jsonResponse, stubFetch } from "@/test/fetch";

import {
  createProvider,
  deleteProvider,
  getProvider,
  listProviderEndpoints,
  listProviders,
  syncProvider,
  updateProvider,
} from "./client";

const fetchMock = stubFetch();

const providerFixture = {
  id: "prov_abc",
  account_id: "acct_1",
  name: "my-alchemy",
  vendor: "alchemy",
  vendor_label: "Alchemy",
  enabled: true,
  sync_enabled: true,
  credential: { has_secret: true },
  settings: {},
  only_networks: [{ chain: "ethereum", network: "mainnet" }],
  ignore_networks: [],
  last_sync_at: "2026-06-30T00:00:00Z",
  last_sync_status: "success",
  last_sync_error: null,
  last_sync_created: 2,
  last_sync_updated: 1,
  last_sync_restored: 0,
  last_sync_archived: 0,
  last_sync_skipped: 0,
  version: 3,
  created_at: "2026-06-01T00:00:00Z",
  modified_at: "2026-06-30T00:00:00Z",
};

const providerDetailFixture = {
  ...providerFixture,
  credential: { has_secret: true, secret: "provider-secret" },
};

describe("V2 providers api client", () => {
  it("lists V2 providers with repeated vendor filters", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        msg: "ok",
        data: {
          page: 1,
          size: 20,
          total: 1,
          max_page: 1,
          items: [providerFixture],
        },
      }),
    );
    const result = await listProviders({ vendor: ["alchemy", "drpc"] });
    expect(result.items[0].credential).toEqual({ has_secret: true });
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toMatch(/\/v2\/providers\?/);
    expect(url).toMatch(/vendor=alchemy/);
    expect(url).toMatch(/vendor=drpc/);
  });

  it("gets one V2 provider", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ msg: "ok", data: providerDetailFixture }),
    );
    expect((await getProvider("prov_abc")).credential.secret).toBe(
      "provider-secret",
    );
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/v2\/providers\/prov_abc$/);
    expect(fetchMock.mock.calls[0][1]?.cache).toBe("no-store");
  });

  it("creates with the V2 credential contract", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ msg: "ok", data: providerDetailFixture }),
    );
    await createProvider({
      name: "my-alchemy",
      vendor: "alchemy",
      credential: { secret: "api-key" },
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/v2\/providers$/);
    expect(JSON.parse(init?.body as string)).toMatchObject({
      credential: { secret: "api-key" },
    });
  });

  it("patches with optimistic version checking", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ msg: "ok", data: providerDetailFixture }),
    );
    await updateProvider("prov_abc", {
      expected_version: 3,
      sync_enabled: false,
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/v2\/providers\/prov_abc$/);
    expect(init?.method).toBe("PATCH");
  });

  it("deletes the V2 resource", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        msg: "ok",
        data: {
          id: "prov_abc",
          version: 4,
          deleted: true,
          archived_endpoints: 2,
          retained_endpoints: 1,
          detached_endpoints: 3,
        },
      }),
    );
    expect(
      (
        await deleteProvider("prov_abc", {
          delete_unreferenced_endpoints: true,
        })
      ).archived_endpoints,
    ).toBe(2);
    expect(fetchMock.mock.calls[0][0]).toMatch(
      /delete_unreferenced_endpoints=true/,
    );
    expect(fetchMock.mock.calls[0][1]?.method).toBe("DELETE");
  });

  it("parses sync and managed endpoint results", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        msg: "ok",
        data: {
          provider_id: "prov_abc",
          status: "success",
          created: 1,
          updated: 0,
          restored: 1,
          archived: 0,
          skipped: 0,
          items: [
            {
              action: "restored",
              endpoint_id: "ep_1",
              external_id: "alchemy:1",
            },
          ],
        },
      }),
    );
    expect((await syncProvider("prov_abc")).restored).toBe(1);

    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        msg: "ok",
        data: {
          page: 1,
          size: 20,
          total: 1,
          max_page: 1,
          items: [
            {
              endpoint: {
                id: "ep_1",
                account_id: "acct_1",
                name: "alchemy-ethereum-mainnet",
                origin_type: "provider",
                provider: {
                  id: "prov_abc",
                  name: "my-alchemy",
                  vendor: "alchemy",
                  vendor_label: "Alchemy",
                },
                provider_external_id: "alchemy:1",
                provider_sync_status: "available",
                provider_last_seen_at: "2026-06-30T00:00:00Z",
                chain: "ethereum",
                network: "mainnet",
                protocol: "jsonrpc",
                url: "***",
                enabled: true,
                auth: { type: "path_api_key", has_secret: true },
                version: 1,
                created_at: "2026-06-30T00:00:00Z",
                modified_at: "2026-06-30T00:00:00Z",
              },
              sync_status: "available",
              external_id: "alchemy:1",
              last_seen_at: "2026-06-30T00:00:00Z",
              archived_at: null,
            },
          ],
        },
      }),
    );
    expect((await listProviderEndpoints("prov_abc")).items[0].endpoint.id).toBe(
      "ep_1",
    );
  });
});
