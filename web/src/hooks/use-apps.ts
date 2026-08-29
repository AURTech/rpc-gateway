import {
  type QueryKey,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect } from "react";

import {
  type CreateRpcAppParams,
  createApp,
  deleteApp,
  getApp,
  type ListAppsParams,
  listAppKeys,
  listApps,
  type RpcAppDetail,
  type RpcAppKeyList,
  type RpcAppList,
  revokeAppKey,
  rotateAppKey,
  type UpdateRpcAppParams,
  updateApp,
} from "@/api/apps/client";

const root = ["apps"] as const;

export const appsKeys = {
  all: root,
  lists: () => [...root, "list"] as const,
  list: (params: ListAppsParams) =>
    [...root, "list", normalizeListParams(params)] as const,
  detail: (id: string) => [...root, "detail", id] as const,
  keys: (id: string) => [...root, "keys", id] as const,
};

function normalizeListParams(params: ListAppsParams) {
  return {
    search: params.search ?? "",
    enabled: params.enabled ?? null,
    provider_id: params.provider_id ?? "",
    start_at: params.start_at ?? "",
    end_at: params.end_at ?? "",
    sort: params.sort ?? "DESC",
    page: params.page ?? 1,
    size: params.size ?? 10,
  };
}

export function useAppsQuery(params: ListAppsParams = {}) {
  return useQuery<RpcAppList>({
    queryKey: appsKeys.list(params) as unknown as QueryKey,
    queryFn: () => listApps(params),
    staleTime: 15_000,
  });
}

/**
 * Scroll-loaded variant of the apps list. Accumulates pages and stops once the
 * last page reaches `max_page`. `staleTime: 0` so re-entering the page or
 * changing the search term always refetches instead of showing a stale
 * accumulation.
 */
export function useInfiniteAppsQuery(params: ListAppsParams = {}) {
  return useInfiniteQuery({
    // Nested under lists() so `invalidateLists` (["apps","list"]) prefix-matches
    // this infinite query and refetches it after create/update/delete.
    queryKey: [
      ...appsKeys.lists(),
      "infinite",
      normalizeListParams(params),
    ] as unknown as QueryKey,
    queryFn: ({ pageParam }) => listApps({ ...params, page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (last) =>
      last.page < last.max_page ? last.page + 1 : undefined,
    staleTime: 0,
  });
}

export function useAppQuery(id: string | null) {
  return useQuery<RpcAppDetail>({
    queryKey: appsKeys.detail(id ?? "") as unknown as QueryKey,
    queryFn: () => getApp(id as string),
    enabled: id !== null && id.length > 0,
  });
}

export function useAppKeysQuery(id: string | null) {
  const query = useQuery<RpcAppKeyList>({
    queryKey: appsKeys.keys(id ?? "") as unknown as QueryKey,
    queryFn: () => listAppKeys(id as string),
    enabled: id !== null && id.length > 0,
    gcTime: 0,
  });
  const { data, refetch } = query;

  useEffect(() => {
    const delay = appKeysGraceRefreshDelay(data);
    if (delay === false) return;

    const timeout = setTimeout(() => {
      void refetch();
    }, delay);
    return () => clearTimeout(timeout);
  }, [data, refetch]);

  return query;
}

const GRACE_EXPIRY_SAFETY_MS = 200;
const EXPIRED_GRACE_CORRECTION_MS = 250;

export function appKeysGraceRefreshDelay(
  data: RpcAppKeyList | undefined,
  now = Date.now(),
): number | false {
  const expirations = (data?.items ?? [])
    .filter((key) => key.state === "grace" && key.expires_at)
    .map((key) => Date.parse(key.expires_at as string))
    .filter(Number.isFinite);

  if (expirations.length === 0) return false;
  if (expirations.some((expiresAt) => expiresAt <= now)) {
    return EXPIRED_GRACE_CORRECTION_MS;
  }

  return Math.min(...expirations) - now + GRACE_EXPIRY_SAFETY_MS;
}

function invalidateLists(qc: ReturnType<typeof useQueryClient>) {
  return qc.invalidateQueries({ queryKey: appsKeys.lists() });
}

export function useCreateAppMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateRpcAppParams) => createApp(input),
    // Creation returns the initial key. Drop mutation data as soon as the
    // observer goes away; the settings query reloads it when needed.
    gcTime: 0,
    onSuccess: () => invalidateLists(qc),
  });
}

export function useUpdateAppMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: UpdateRpcAppParams }) =>
      updateApp(id, input),
    onSuccess: (data) => {
      invalidateLists(qc);
      qc.setQueryData(appsKeys.detail(data.id), data);
    },
  });
}

export function useDeleteAppMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteApp(id),
    onSuccess: () => invalidateLists(qc),
  });
}

export function useRotateAppKeyMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (appId: string) => rotateAppKey(appId),
    gcTime: 0,
    onSuccess: (_data, appId) =>
      qc.invalidateQueries({ queryKey: appsKeys.keys(appId) }),
  });
}

export function useRevokeAppKeyMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ appId, keyId }: { appId: string; keyId: string }) =>
      revokeAppKey(appId, keyId),
    onSuccess: (key, { appId }) => {
      qc.setQueryData<RpcAppKeyList>(appsKeys.keys(appId), (current) =>
        current
          ? {
              ...current,
              items: current.items.map((item) =>
                item.id === key.id ? key : item,
              ),
            }
          : current,
      );
      return qc.invalidateQueries({ queryKey: appsKeys.keys(appId) });
    },
  });
}
