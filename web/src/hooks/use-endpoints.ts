import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  bulkDeleteEndpoints,
  type CreateEndpointInput,
  createEndpoint,
  deleteEndpoint,
  type EndpointDetail,
  getEndpoint,
  type ListEndpointsParams,
  listEndpointAuditEvents,
  listEndpoints,
  type UpdateEndpointInput,
  updateEndpoint,
} from "@/api/endpoints/client";

const root = ["endpoints"] as const;

export const endpointsKeys = {
  all: root,
  lists: () => [...root, "list"] as const,
  list: (params: ListEndpointsParams) => [...root, "list", params] as const,
  detail: (id: string) => [...root, "detail", id] as const,
  audit: (id: string, page: number, size: number) =>
    [...root, "audit", id, page, size] as const,
};

export function useEndpointsQuery(params: ListEndpointsParams = {}) {
  return useQuery({
    queryKey: endpointsKeys.list(params),
    queryFn: () => listEndpoints(params),
    staleTime: 15_000,
  });
}

export function useEndpointQuery(id: string | null) {
  return useQuery({
    queryKey: endpointsKeys.detail(id ?? ""),
    queryFn: () => getEndpoint(id as string),
    enabled: Boolean(id),
    gcTime: 0,
  });
}

export function useEndpointAuditQuery(id: string | null, page = 1, size = 20) {
  return useQuery({
    queryKey: endpointsKeys.audit(id ?? "", page, size),
    queryFn: () => listEndpointAuditEvents(id as string, page, size),
    enabled: Boolean(id),
  });
}

function cacheEndpoint(
  queryClient: ReturnType<typeof useQueryClient>,
  endpoint: EndpointDetail,
) {
  queryClient.setQueryData(endpointsKeys.detail(endpoint.id), endpoint);
}

export function useCreateEndpointMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateEndpointInput) => createEndpoint(input),
    onSuccess: (endpoint) => {
      cacheEndpoint(queryClient, endpoint);
      queryClient.invalidateQueries({ queryKey: endpointsKeys.lists() });
    },
  });
}

export function useUpdateEndpointMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: UpdateEndpointInput }) =>
      updateEndpoint(id, input),
    onSuccess: (endpoint) => {
      cacheEndpoint(queryClient, endpoint);
      queryClient.invalidateQueries({ queryKey: endpointsKeys.lists() });
      queryClient.invalidateQueries({
        queryKey: [...root, "audit", endpoint.id],
      });
    },
  });
}

export function useDeleteEndpointMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteEndpoint(id),
    onSuccess: (result) => {
      queryClient.removeQueries({ queryKey: endpointsKeys.detail(result.id) });
      queryClient.invalidateQueries({ queryKey: endpointsKeys.lists() });
    },
  });
}

export function useBulkDeleteEndpointsMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (endpointIds: readonly string[]) =>
      bulkDeleteEndpoints(endpointIds),
    onSuccess: (result) => {
      for (const endpoint of result.deleted) {
        queryClient.removeQueries({
          queryKey: endpointsKeys.detail(endpoint.id),
        });
      }
      queryClient.invalidateQueries({ queryKey: endpointsKeys.lists() });
    },
  });
}
