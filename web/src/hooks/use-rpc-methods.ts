import { type QueryKey, useQuery } from "@tanstack/react-query";

import {
  type ListRpcMethodsParams,
  listRpcMethods,
  type RpcMethodCatalog,
} from "@/api/rpc-methods/client";

const root = ["rpc-methods"] as const;

export const rpcMethodsKeys = {
  all: root,
  list: (params: ListRpcMethodsParams) =>
    [...root, normalizeListParams(params)] as const,
};

function normalizeListParams(
  params: ListRpcMethodsParams,
): Record<string, string | undefined> {
  return {
    protocol: params.protocol,
  };
}

export function useRpcMethodsQuery(params: ListRpcMethodsParams = {}) {
  return useQuery<RpcMethodCatalog>({
    queryKey: rpcMethodsKeys.list(params) as unknown as QueryKey,
    queryFn: () => listRpcMethods(params),
    staleTime: 60_000,
  });
}
