import {
  type QueryKey,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  type BulkUpdateGatewayParams,
  bulkUpdateGateways,
  getGateway,
  type ListGatewaysParams,
  listGateways,
  type RpcGatewayDetail,
  type RpcGatewayList,
  type UpdateRpcGatewayParams,
  updateGateway,
} from "@/api/gateways/client";

const root = ["gateways"] as const;

export const gatewaysKeys = {
  all: root,
  lists: () => [...root, "list"] as const,
  list: (params: ListGatewaysParams) =>
    [...root, "list", normalizeListParams(params)] as const,
  detail: (id: string) => [...root, "detail", id] as const,
};

function normalizeListParams(
  params: ListGatewaysParams,
): Record<string, string | number | boolean | readonly string[]> {
  const out: Record<string, string | number | boolean | readonly string[]> = {};
  out.search = params.search ?? "";
  if (params.app_id !== undefined) out.app_id = params.app_id;
  if (params.chain !== undefined) {
    // Sort array values so semantically-equivalent filter sets (`['eth','pol']`
    // vs `['pol','eth']`) hash to the same React Query cache key.
    out.chain = Array.isArray(params.chain)
      ? params.chain.toSorted()
      : params.chain;
  }
  if (params.network !== undefined) {
    out.network = Array.isArray(params.network)
      ? params.network.toSorted()
      : params.network;
  }
  if (params.enabled !== undefined) out.enabled = params.enabled;
  if (params.start_at !== undefined) out.start_at = params.start_at;
  if (params.end_at !== undefined) out.end_at = params.end_at;
  out.sort = params.sort ?? "DESC";
  out.page = params.page ?? 1;
  out.size = params.size ?? 10;
  return out;
}

export function useGatewaysQuery(params: ListGatewaysParams = {}) {
  return useQuery<RpcGatewayList>({
    queryKey: gatewaysKeys.list(params) as unknown as QueryKey,
    queryFn: () => listGateways(params),
    staleTime: 15_000,
  });
}

export function useGatewayQuery(id: string | null) {
  return useQuery<RpcGatewayDetail>({
    queryKey: gatewaysKeys.detail(id ?? "") as unknown as QueryKey,
    queryFn: () => getGateway(id as string),
    enabled: id !== null && id.length > 0,
  });
}

function invalidateLists(qc: ReturnType<typeof useQueryClient>) {
  return qc.invalidateQueries({ queryKey: gatewaysKeys.lists() });
}

function updateGatewayCaches(
  qc: ReturnType<typeof useQueryClient>,
  gateways: readonly RpcGatewayDetail[],
) {
  const updates = new Map(gateways.map((gateway) => [gateway.id, gateway]));
  for (const gateway of gateways) {
    qc.setQueryData(gatewaysKeys.detail(gateway.id), gateway);
  }
  for (const [queryKey, cached] of qc.getQueriesData<RpcGatewayList>({
    queryKey: gatewaysKeys.lists(),
  })) {
    if (!cached) continue;
    const params = queryKey[2] as
      | Record<string, string | number | boolean | readonly string[]>
      | undefined;
    let removed = 0;
    const items = cached.items.flatMap((gateway) => {
      const updated = updates.get(gateway.id);
      if (!updated) return [gateway];
      if (
        typeof params?.enabled === "boolean" &&
        updated.enabled !== params.enabled
      ) {
        removed += 1;
        return [];
      }
      return [updated];
    });
    const total = Math.max(0, cached.total - removed);
    const maxPage = total === 0 ? 0 : Math.ceil(total / cached.size);
    qc.setQueryData(queryKey, {
      ...cached,
      total,
      max_page: maxPage,
      items,
    });
  }
}

export function useUpdateGatewayMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      input,
    }: {
      id: string;
      input: UpdateRpcGatewayParams;
    }) => updateGateway(id, input),
    onSuccess: (data) => {
      updateGatewayCaches(qc, [data]);
      invalidateLists(qc);
    },
  });
}

export function useBulkUpdateGatewaysMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      appId,
      ...input
    }: BulkUpdateGatewayParams & { appId: string }) =>
      bulkUpdateGateways(appId, input),
    onSuccess: (data) => {
      updateGatewayCaches(qc, data.items);
      void qc.invalidateQueries({
        queryKey: gatewaysKeys.lists(),
        refetchType: "none",
      });
    },
  });
}
