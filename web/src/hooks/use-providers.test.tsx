import { useInfiniteQuery } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  type RpcProviderBase,
  type RpcProviderList,
  type RpcProviderSyncResult,
  syncProvider,
} from "@/api/providers/client";
import { makeProvider } from "@/test/fixtures";
import { createTestQueryClient, queryWrapper } from "@/test/query";

import { providersKeys, useSyncProviderMutation } from "./use-providers";

vi.mock("@/api/providers/client", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/api/providers/client")>();
  return {
    ...actual,
    syncProvider: vi.fn(),
  };
});

const syncProviderMock = vi.mocked(syncProvider);

function makeList(provider: RpcProviderBase): RpcProviderList {
  return {
    page: 1,
    size: 12,
    total: 1,
    max_page: 1,
    items: [provider],
  };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("useSyncProviderMutation", () => {
  it("refetches the active infinite provider list after a successful sync", async () => {
    const queryClient = createTestQueryClient();
    const beforeSync = makeList(makeProvider());
    const afterSync = makeList(
      makeProvider({
        last_sync_at: "2026-07-28T07:00:00Z",
        last_sync_status: "success",
        last_sync_status_label: "Success",
      }),
    );
    const listQuery = vi
      .fn<() => Promise<RpcProviderList>>()
      .mockResolvedValueOnce(beforeSync)
      .mockResolvedValue(afterSync);
    const syncResult: RpcProviderSyncResult = {
      provider_id: "prov_1",
      status: "success",
      status_label: "Success",
      created: 0,
      updated: 0,
      restored: 0,
      archived: 0,
      skipped: 0,
      route_targets_added: 0,
      route_targets_removed: 0,
      route_targets_skipped: 0,
      items: [],
    };
    syncProviderMock.mockResolvedValue(syncResult);

    const wrapper = queryWrapper(queryClient);
    const { result } = renderHook(
      () => {
        const list = useInfiniteQuery({
          queryKey: providersKeys.infiniteList({ size: 12 }),
          queryFn: listQuery,
          initialPageParam: 1,
          getNextPageParam: () => undefined,
        });
        const sync = useSyncProviderMutation();
        return { list, sync };
      },
      { wrapper },
    );

    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));
    expect(result.current.list.data?.pages[0]?.items[0]?.last_sync_status).toBe(
      "never",
    );

    await act(async () => {
      await result.current.sync.mutateAsync("prov_1");
    });

    await waitFor(() => expect(listQuery).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(
        result.current.list.data?.pages[0]?.items[0]?.last_sync_status,
      ).toBe("success"),
    );
  });
});
