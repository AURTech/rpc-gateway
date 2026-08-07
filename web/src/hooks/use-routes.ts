import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type CreateMethodRouteInput,
  createMethodRoute,
  deleteMethodRoute,
  getDefaultRoute,
  type JsonRpcMethodRouteList,
  type JsonRpcRoute,
  listMethodRoutes,
  putDefaultRoute,
  type ReplaceDefaultRouteInput,
  type ReplaceMethodRouteInput,
  updateMethodRoute,
} from "@/api/jsonrpc-routes/client";
import { gatewaysKeys } from "@/hooks/use-gateways";

const root = ["jsonrpc-routes"] as const;

export const routesKeys = {
  all: root,
  default: (gatewayId: string) => [...root, "default", gatewayId] as const,
  methods: (gatewayId: string) => [...root, "methods", gatewayId] as const,
};

export function useDefaultRouteQuery(gatewayId: string | null) {
  return useQuery<JsonRpcRoute>({
    queryKey: routesKeys.default(gatewayId ?? ""),
    queryFn: () => getDefaultRoute(gatewayId as string),
    enabled: gatewayId !== null && gatewayId.length > 0,
    staleTime: 15_000,
    // A gateway predating the default-route seeding would 404 here; readiness
    // treats that as "unconfigured" rather than surfacing a global error toast.
    meta: { skipGlobalErrorToast: true },
  });
}

export function useMethodRoutesQuery(gatewayId: string | null) {
  return useQuery<JsonRpcMethodRouteList>({
    queryKey: routesKeys.methods(gatewayId ?? ""),
    queryFn: () => listMethodRoutes(gatewayId as string),
    enabled: gatewayId !== null && gatewayId.length > 0,
    staleTime: 15_000,
  });
}

export function useReplaceDefaultRouteMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      gatewayId,
      input,
    }: {
      gatewayId: string;
      input: ReplaceDefaultRouteInput;
    }) => putDefaultRoute(gatewayId, input),
    meta: { skipGlobalErrorToast: true },
    onSuccess: (route) => {
      qc.setQueryData(routesKeys.default(route.gateway_id), route);
      // The default route's target count drives the gateway readiness badge.
      qc.invalidateQueries({ queryKey: gatewaysKeys.detail(route.gateway_id) });
      qc.invalidateQueries({ queryKey: gatewaysKeys.lists() });
    },
  });
}

export function useCreateMethodRouteMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      gatewayId,
      input,
    }: {
      gatewayId: string;
      input: CreateMethodRouteInput;
    }) => createMethodRoute(gatewayId, input),
    meta: { skipGlobalErrorToast: true },
    onSuccess: (route) => {
      qc.invalidateQueries({ queryKey: routesKeys.methods(route.gateway_id) });
    },
  });
}

export function useUpdateMethodRouteMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      gatewayId,
      routeId,
      input,
    }: {
      gatewayId: string;
      routeId: string;
      input: ReplaceMethodRouteInput;
    }) => updateMethodRoute(gatewayId, routeId, input),
    meta: { skipGlobalErrorToast: true },
    onSuccess: (route) => {
      qc.invalidateQueries({ queryKey: routesKeys.methods(route.gateway_id) });
    },
  });
}

export function useDeleteMethodRouteMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      gatewayId,
      routeId,
      expectedVersion,
    }: {
      gatewayId: string;
      routeId: string;
      expectedVersion: number;
    }) => deleteMethodRoute(gatewayId, routeId, expectedVersion),
    meta: { skipGlobalErrorToast: true },
    onSuccess: (route) => {
      qc.invalidateQueries({ queryKey: routesKeys.methods(route.gateway_id) });
    },
  });
}
