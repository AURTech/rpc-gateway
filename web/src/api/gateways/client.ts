import { z } from "zod/v4";

import { api } from "@/api/client";
import { RPC_CHAINS, RPC_NETWORKS } from "@/lib/rpc-chain";

const rpcChainSchema = z.enum(RPC_CHAINS);
const rpcNetworkSchema = z.enum(RPC_NETWORKS);

const rpcGatewayTransportSchema = z.enum(["jsonrpc", "http_api"]);
const rpcGatewayAccessPointSchema = z.object({
  transport: rpcGatewayTransportSchema,
  url: z.string().min(1),
});

const rpcGatewayWireSchema = z.object({
  id: z.string(),
  app_id: z.string(),
  app_name: z.string(),
  name: z.string(),
  chain: rpcChainSchema,
  network: rpcNetworkSchema,
  enabled: z.boolean(),
  effective_enabled: z.boolean(),
  version: z.number().int().positive(),
  access_points: z.array(rpcGatewayAccessPointSchema),
  created_at: z.string(),
  modified_at: z.string(),
});

const rpcGatewayBaseSchema = rpcGatewayWireSchema;

const rpcGatewayDetailSchema = rpcGatewayBaseSchema;

const rpcGatewayListSchema = z.object({
  page: z.number().int(),
  size: z.number().int(),
  total: z.number().int(),
  max_page: z.number().int(),
  items: z.array(rpcGatewayBaseSchema),
});

const bulkUpdateGatewayResultSchema = z.object({
  total: z.number().int(),
  items: z.array(rpcGatewayDetailSchema),
});

const envelope = <T extends z.ZodType>(data: T) =>
  z.object({ msg: z.string(), data });

export type RpcChain = z.infer<typeof rpcChainSchema>;
export type RpcNetwork = z.infer<typeof rpcNetworkSchema>;
export type RpcGatewayTransport = z.infer<typeof rpcGatewayTransportSchema>;
export type RpcGatewayAccessPoint = z.infer<typeof rpcGatewayAccessPointSchema>;
export type RpcGatewayBase = z.infer<typeof rpcGatewayBaseSchema>;
export type RpcGatewayDetail = z.infer<typeof rpcGatewayDetailSchema>;
export type RpcGatewayList = z.infer<typeof rpcGatewayListSchema>;
export type BulkUpdateGatewayResult = z.infer<
  typeof bulkUpdateGatewayResultSchema
>;

export type ListGatewaysParams = {
  search?: string | null;
  /** Restrict to gateways owned by this app. */
  app_id?: string;
  /** Single chain or list of chains; serialized as `?chain=a&chain=b`. */
  chain?: RpcChain | RpcChain[];
  /** Single network or list of networks; serialized as `?network=a&network=b`. */
  network?: RpcNetwork | RpcNetwork[];
  enabled?: boolean;
  /** Lower bound on `created_at`, inclusive; ISO 8601 with timezone. */
  start_at?: string;
  /** Upper bound on `created_at`, exclusive; ISO 8601 with timezone. */
  end_at?: string;
  /** `created_at` sort direction. Server default `DESC`. */
  sort?: "ASC" | "DESC";
  page?: number;
  size?: number;
};

export type UpdateRpcGatewayParams = {
  expected_version: number;
  name?: string;
  enabled?: boolean;
};

export type BulkUpdateGatewayParams = {
  enabled: boolean;
  gateways: Array<{ id: string; expected_version: number }>;
};

function toListParams(
  input: ListGatewaysParams,
): Record<string, string | string[]> {
  const params: Record<string, string | string[]> = {};
  if (input.search) params.search = input.search;
  if (input.app_id) params.app_id = input.app_id;
  if (input.chain !== undefined) {
    params.chain = Array.isArray(input.chain) ? input.chain : input.chain;
  }
  if (input.network !== undefined) {
    params.network = Array.isArray(input.network)
      ? input.network
      : input.network;
  }
  if (input.enabled !== undefined) params.enabled = String(input.enabled);
  if (input.start_at !== undefined) params.start_at = input.start_at;
  if (input.end_at !== undefined) params.end_at = input.end_at;
  if (input.sort !== undefined) params.sort = input.sort;
  if (input.page) params.page = String(input.page);
  if (input.size) params.size = String(input.size);
  return params;
}

const GATEWAYS_BASE = "/v2/gateways";

export async function listGateways(
  input: ListGatewaysParams = {},
): Promise<RpcGatewayList> {
  const response = await api.get<unknown>(GATEWAYS_BASE, {
    params: toListParams(input),
  });
  return envelope(rpcGatewayListSchema).parse(response).data;
}

export async function getGateway(id: string): Promise<RpcGatewayDetail> {
  const response = await api.get<unknown>(`${GATEWAYS_BASE}/${id}`);
  return envelope(rpcGatewayDetailSchema).parse(response).data;
}

export async function updateGateway(
  id: string,
  input: UpdateRpcGatewayParams,
): Promise<RpcGatewayDetail> {
  const response = await api.patch<unknown>(`${GATEWAYS_BASE}/${id}`, input);
  return envelope(rpcGatewayDetailSchema).parse(response).data;
}

export async function bulkUpdateGateways(
  appId: string,
  input: BulkUpdateGatewayParams,
): Promise<BulkUpdateGatewayResult> {
  const response = await api.patch<unknown>(
    `/v2/apps/${appId}/gateways`,
    input,
  );
  return envelope(bulkUpdateGatewayResultSchema).parse(response).data;
}
