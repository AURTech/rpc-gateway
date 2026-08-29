import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  bulkDeleteEndpoints,
  type CreateEndpointInput,
  checkEndpointHealth,
  createEndpoint,
  deleteEndpoint,
  deleteEndpointRouteBinding,
  type Endpoint,
  type EndpointDetail,
  type EndpointList,
  getEndpoint,
  type ListEndpointsParams,
  listEndpointRouteBindings,
  listEndpoints,
  type UpdateEndpointInput,
  updateEndpoint,
} from "@/api/endpoints/client";
import { gatewaysKeys } from "@/hooks/use-gateways";
import { httpApiRoutesKeys } from "@/hooks/use-http-api-routes";
import { routesKeys } from "@/hooks/use-routes";

const root = ["endpoints"] as const;

export const endpointsKeys = {
  all: root,
  lists: () => [...root, "list"] as const,
  list: (params: ListEndpointsParams) => [...root, "list", params] as const,
  detail: (id: string) => [...root, "detail", id] as const,
  bindings: (id: string) => [...root, "bindings", id] as const,
};

export function useEndpointsQuery(params: ListEndpointsParams = {}) {
  return useQuery({
    queryKey: endpointsKeys.list(params),
    queryFn: () => listEndpoints(params),
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });
}

export function endpointDetailQueryOptions(id: string) {
  return {
    queryKey: endpointsKeys.detail(id),
    queryFn: () => getEndpoint(id),
    staleTime: 30_000,
    gcTime: 5 * 60_000,
  } as const;
}

export function useEndpointQuery(
  id: string | null,
  placeholderData?: Endpoint,
) {
  return useQuery({
    ...endpointDetailQueryOptions(id ?? ""),
    enabled: Boolean(id),
    placeholderData,
  });
}

export function useEndpointRouteBindingsQuery(id: string | null) {
  return useQuery({
    queryKey: endpointsKeys.bindings(id ?? ""),
    queryFn: () => listEndpointRouteBindings(id as string),
    enabled: Boolean(id),
    staleTime: 15_000,
  });
}

export function useCheckEndpointHealthMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => checkEndpointHealth(id),
    onSuccess: (health, id) => {
      queryClient.setQueriesData<EndpointList>(
        { queryKey: endpointsKeys.lists() },
        (value) =>
          value
            ? {
                ...value,
                items: value.items.map((endpoint) =>
                  endpoint.id === id ? { ...endpoint, health } : endpoint,
                ),
              }
            : value,
      );
      queryClient.setQueryData<EndpointDetail>(
        endpointsKeys.detail(id),
        (value) => (value ? { ...value, health } : value),
      );
    },
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

export function useDeleteEndpointRouteBindingMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      endpointId,
      binding,
    }: {
      endpointId: string;
      binding: Parameters<typeof deleteEndpointRouteBinding>[1];
    }) => deleteEndpointRouteBinding(endpointId, binding),
    onSuccess: (result) => {
      queryClient.invalidateQueries({
        queryKey: endpointsKeys.bindings(result.endpoint_id),
      });
      queryClient.invalidateQueries({ queryKey: gatewaysKeys.all });
      queryClient.invalidateQueries({ queryKey: routesKeys.all });
      queryClient.invalidateQueries({ queryKey: httpApiRoutesKeys.all });
    },
  });
}
