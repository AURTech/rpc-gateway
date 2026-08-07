import {
  type QueryKey,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  type CreateProviderInput,
  createProvider,
  deleteProvider,
  getProvider,
  type ListProvidersParams,
  listProviderEndpoints,
  listProviders,
  type ProviderEndpointList,
  type RpcProvider,
  type RpcProviderList,
  type RpcProviderSyncResult,
  syncProvider,
  type UpdateProviderInput,
  updateProvider,
} from "@/api/providers/client";
import { endpointsKeys } from "@/hooks/use-endpoints";

const root = ["providers"] as const;

export const providersKeys = {
  all: root,
  lists: () => [...root, "list"] as const,
  list: (params: ListProvidersParams) =>
    [...root, "list", normalizeListParams(params)] as const,
  infiniteList: (params: Omit<ListProvidersParams, "page">) =>
    [...root, "list", "infinite", normalizeListParams(params)] as const,
  detail: (id: string) => [...root, "detail", id] as const,
  endpoints: (id: string) => [...root, "endpoints", id] as const,
};

function normalizeListParams(
  params: ListProvidersParams,
): Record<string, string | number | boolean | readonly string[]> {
  const out: Record<string, string | number | boolean | readonly string[]> = {};
  if (params.vendor !== undefined) out.vendor = params.vendor;
  if (params.enabled !== undefined) out.enabled = params.enabled;
  if (params.sync_enabled !== undefined) out.sync_enabled = params.sync_enabled;
  out.page = params.page ?? 1;
  out.size = params.size ?? 10;
  return out;
}

export function useProvidersQuery(params: ListProvidersParams = {}) {
  return useQuery<RpcProviderList>({
    queryKey: providersKeys.list(params) as unknown as QueryKey,
    queryFn: () => listProviders(params),
    staleTime: 15_000,
  });
}

export function useProviderQuery(id: string | null) {
  return useQuery<RpcProvider>({
    queryKey: providersKeys.detail(id ?? "") as unknown as QueryKey,
    queryFn: () => getProvider(id as string),
    enabled: id !== null && id.length > 0,
    gcTime: 0,
  });
}

export function useProviderEndpointsQuery(id: string | null) {
  return useQuery<ProviderEndpointList>({
    queryKey: providersKeys.endpoints(id ?? "") as unknown as QueryKey,
    queryFn: () => listProviderEndpoints(id as string),
    enabled: id !== null && id.length > 0,
  });
}

function invalidateLists(qc: ReturnType<typeof useQueryClient>) {
  return qc.invalidateQueries({ queryKey: providersKeys.lists() });
}

function cacheDetail(
  qc: ReturnType<typeof useQueryClient>,
  provider: RpcProvider,
) {
  qc.setQueryData(providersKeys.detail(provider.id), provider);
}

export function useCreateProviderMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateProviderInput) => createProvider(input),
    onSuccess: (data) => {
      invalidateLists(qc);
      cacheDetail(qc, data);
    },
  });
}

export function useUpdateProviderMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: UpdateProviderInput }) =>
      updateProvider(id, input),
    onSuccess: (data) => {
      invalidateLists(qc);
      cacheDetail(qc, data);
    },
  });
}

export function useDeleteProviderMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteProvider(id),
    onSuccess: (_data, id) => {
      invalidateLists(qc);
      qc.invalidateQueries({ queryKey: endpointsKeys.lists() });
      qc.removeQueries({ queryKey: providersKeys.detail(id) });
      qc.removeQueries({ queryKey: providersKeys.endpoints(id) });
    },
  });
}

export function useSyncProviderMutation() {
  const qc = useQueryClient();
  return useMutation<RpcProviderSyncResult, Error, string>({
    mutationFn: (id: string) => syncProvider(id),
    onSuccess: (_data, id) => {
      // Refresh sync state, managed endpoints, and the global Endpoint Registry.
      invalidateLists(qc);
      qc.invalidateQueries({ queryKey: providersKeys.detail(id) });
      qc.invalidateQueries({ queryKey: providersKeys.endpoints(id) });
      qc.invalidateQueries({ queryKey: endpointsKeys.lists() });
    },
  });
}
