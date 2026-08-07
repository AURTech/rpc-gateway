import { z } from "zod/v4";

import { api } from "@/api/client";

/** Endpoint trust levels a route may require (mirrors backend `EndpointTrustLevel`). */
export const ENDPOINT_TRUST_LEVELS = [
  "unverified",
  "trusted",
  "authoritative",
] as const;

/** JSON-RPC forwarding retry policies (mirrors backend `JsonRpcRetryPolicy`). */
export const JSONRPC_RETRY_POLICIES = ["safe_only", "idempotent"] as const;

/** Routing strategy discriminator (mirrors backend `JsonRpcRoutingStrategyType`). */
export const JSONRPC_STRATEGY_TYPES = [
  "priority_failover",
  "load_balance",
] as const;

const trustLevelSchema = z.enum(ENDPOINT_TRUST_LEVELS);
const retryPolicySchema = z.enum(JSONRPC_RETRY_POLICIES);

// --- Response strategy (server includes `position`; `weight` only on load_balance) ---
const loadBalanceTargetItemSchema = z.object({
  endpoint_id: z.string(),
  position: z.number().int(),
  weight: z.number().int(),
});
const priorityFailoverTargetItemSchema = z.object({
  endpoint_id: z.string(),
  position: z.number().int(),
});
const strategyItemSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("load_balance"),
    targets: z.array(loadBalanceTargetItemSchema),
  }),
  z.object({
    type: z.literal("priority_failover"),
    targets: z.array(priorityFailoverTargetItemSchema),
  }),
]);

const jsonRpcRouteSchema = z.object({
  id: z.string(),
  gateway_id: z.string(),
  methods: z.array(z.string()),
  is_default: z.boolean(),
  minimum_trust: trustLevelSchema,
  max_latency_ms: z.number().nullable(),
  max_attempts: z.number().int(),
  retry_policy: retryPolicySchema,
  strategy: strategyItemSchema,
  version: z.number().int().positive(),
  created_at: z.string(),
  modified_at: z.string(),
});

const methodRouteListSchema = z.object({
  total: z.number().int(),
  items: z.array(jsonRpcRouteSchema),
});

const envelope = <T extends z.ZodType>(data: T) =>
  z.object({ msg: z.string(), data });

export type EndpointTrustLevel = z.infer<typeof trustLevelSchema>;
export type JsonRpcRetryPolicy = z.infer<typeof retryPolicySchema>;
export type JsonRpcStrategyType = (typeof JSONRPC_STRATEGY_TYPES)[number];
export type JsonRpcRoute = z.infer<typeof jsonRpcRouteSchema>;
export type JsonRpcMethodRouteList = z.infer<typeof methodRouteListSchema>;

// --- Write payloads (no `position`; server derives it from array order) ---
export type LoadBalanceTargetInput = { endpoint_id: string; weight: number };
export type PriorityFailoverTargetInput = { endpoint_id: string };

export type JsonRpcStrategyInput =
  | { type: "load_balance"; targets: LoadBalanceTargetInput[] }
  | { type: "priority_failover"; targets: PriorityFailoverTargetInput[] };

/** Policy + strategy shared by every route write. */
export type RouteValuesInput = {
  minimum_trust: EndpointTrustLevel;
  max_latency_ms: number | null;
  max_attempts: number;
  retry_policy: JsonRpcRetryPolicy;
  strategy: JsonRpcStrategyInput;
};

export type ReplaceDefaultRouteInput = RouteValuesInput & {
  expected_version: number;
};

export type CreateMethodRouteInput = RouteValuesInput & {
  methods: string[];
};

export type ReplaceMethodRouteInput = CreateMethodRouteInput & {
  expected_version: number;
};

function base(gatewayId: string): string {
  return `/v2/gateways/${gatewayId}`;
}

export async function getDefaultRoute(
  gatewayId: string,
): Promise<JsonRpcRoute> {
  const response = await api.get<unknown>(`${base(gatewayId)}/jsonrpc-route`);
  return envelope(jsonRpcRouteSchema).parse(response).data;
}

export async function putDefaultRoute(
  gatewayId: string,
  input: ReplaceDefaultRouteInput,
): Promise<JsonRpcRoute> {
  const response = await api.put<unknown>(
    `${base(gatewayId)}/jsonrpc-route`,
    input,
  );
  return envelope(jsonRpcRouteSchema).parse(response).data;
}

export async function listMethodRoutes(
  gatewayId: string,
): Promise<JsonRpcMethodRouteList> {
  const response = await api.get<unknown>(
    `${base(gatewayId)}/jsonrpc-method-routes`,
  );
  return envelope(methodRouteListSchema).parse(response).data;
}

export async function createMethodRoute(
  gatewayId: string,
  input: CreateMethodRouteInput,
): Promise<JsonRpcRoute> {
  const response = await api.post<unknown>(
    `${base(gatewayId)}/jsonrpc-method-routes`,
    input,
  );
  return envelope(jsonRpcRouteSchema).parse(response).data;
}

export async function updateMethodRoute(
  gatewayId: string,
  routeId: string,
  input: ReplaceMethodRouteInput,
): Promise<JsonRpcRoute> {
  const response = await api.put<unknown>(
    `${base(gatewayId)}/jsonrpc-method-routes/${routeId}`,
    input,
  );
  return envelope(jsonRpcRouteSchema).parse(response).data;
}

export async function deleteMethodRoute(
  gatewayId: string,
  routeId: string,
  expectedVersion: number,
): Promise<JsonRpcRoute> {
  const response = await api.delete<unknown>(
    `${base(gatewayId)}/jsonrpc-method-routes/${routeId}`,
    { params: { expected_version: String(expectedVersion) } },
  );
  return envelope(jsonRpcRouteSchema).parse(response).data;
}
