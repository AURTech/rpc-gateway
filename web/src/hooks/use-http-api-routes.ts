import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getHttpApiRoute,
  putHttpApiRoute,
  type ReplaceHttpApiRouteInput,
} from "@/api/http-api-routes/client";
import { gatewaysKeys } from "@/hooks/use-gateways";

const root = ["http-api-routes"] as const;

export const httpApiRoutesKeys = {
  all: root,
  detail: (gatewayId: string) => [...root, gatewayId] as const,
};

export function useHttpApiRouteQuery(gatewayId: string | null) {
  return useQuery({
    queryKey: httpApiRoutesKeys.detail(gatewayId ?? ""),
    queryFn: () => getHttpApiRoute(gatewayId as string),
    enabled: gatewayId !== null && gatewayId.length > 0,
    staleTime: 15_000,
    meta: { skipGlobalErrorToast: true },
  });
}

export function useReplaceHttpApiRouteMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      gatewayId,
      input,
    }: {
      gatewayId: string;
      input: ReplaceHttpApiRouteInput;
    }) => putHttpApiRoute(gatewayId, input),
    meta: { skipGlobalErrorToast: true },
    onSuccess: (route) => {
      queryClient.setQueryData(
        httpApiRoutesKeys.detail(route.gateway_id),
        route,
      );
      queryClient.invalidateQueries({
        queryKey: gatewaysKeys.detail(route.gateway_id),
      });
      queryClient.invalidateQueries({ queryKey: gatewaysKeys.lists() });
    },
  });
}
