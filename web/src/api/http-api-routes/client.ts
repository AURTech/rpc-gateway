import { z } from "zod/v4";

import { api } from "@/api/client";

export const HTTP_API_STRATEGY_TYPES = [
  "priority_failover",
  "load_balance",
] as const;

const trustLevelSchema = z.enum(["unverified", "trusted", "authoritative"]);
const retryPolicySchema = z.enum(["safe_only", "idempotent"]);

const loadBalanceTargetSchema = z.object({
  endpoint_id: z.string(),
  position: z.number().int(),
  weight: z.number().int(),
});
const priorityTargetSchema = z.object({
  endpoint_id: z.string(),
  position: z.number().int(),
});
const strategySchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("load_balance"),
    targets: z.array(loadBalanceTargetSchema),
  }),
  z.object({
    type: z.literal("priority_failover"),
    targets: z.array(priorityTargetSchema),
  }),
]);

const httpApiRouteSchema = z.object({
  id: z.string(),
  gateway_id: z.string(),
  minimum_trust: trustLevelSchema,
  max_latency_ms: z.number().nullable(),
  max_attempts: z.number().int(),
  retry_policy: retryPolicySchema,
  strategy: strategySchema,
  version: z.number().int().positive(),
  created_at: z.string(),
  modified_at: z.string(),
});

const envelope = z.object({ msg: z.string(), data: httpApiRouteSchema });

export type HttpApiStrategyType = (typeof HTTP_API_STRATEGY_TYPES)[number];
export type HttpApiRoute = z.infer<typeof httpApiRouteSchema>;
export type HttpApiStrategyInput =
  | {
      type: "load_balance";
      targets: Array<{ endpoint_id: string; weight: number }>;
    }
  | {
      type: "priority_failover";
      targets: Array<{ endpoint_id: string }>;
    };

export type ReplaceHttpApiRouteInput = {
  expected_version: number;
  minimum_trust: HttpApiRoute["minimum_trust"];
  max_latency_ms: number | null;
  max_attempts: number;
  retry_policy: HttpApiRoute["retry_policy"];
  strategy: HttpApiStrategyInput;
};

function routeUrl(gatewayId: string): string {
  return `/v2/gateways/${gatewayId}/http-api-route`;
}

export async function getHttpApiRoute(
  gatewayId: string,
): Promise<HttpApiRoute> {
  return envelope.parse(await api.get<unknown>(routeUrl(gatewayId))).data;
}

export async function putHttpApiRoute(
  gatewayId: string,
  input: ReplaceHttpApiRouteInput,
): Promise<HttpApiRoute> {
  return envelope.parse(await api.put<unknown>(routeUrl(gatewayId), input))
    .data;
}
