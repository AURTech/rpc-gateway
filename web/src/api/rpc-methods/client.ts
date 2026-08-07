import { z } from "zod/v4";

import { api } from "@/api/client";

export const RPC_METHOD_PROTOCOLS = ["evm", "svm", "utxo", "tron"] as const;
export type RpcMethodProtocol = (typeof RPC_METHOD_PROTOCOLS)[number];

export const RPC_METHOD_RISKS = ["read", "write", "sensitive"] as const;
export type RpcMethodRisk = (typeof RPC_METHOD_RISKS)[number];

const rpcMethodProtocolSchema = z.enum(RPC_METHOD_PROTOCOLS);
const rpcMethodRiskSchema = z.enum(RPC_METHOD_RISKS);

const rpcMethodSourceSchema = z.object({
  label: z.string(),
  url: z.string(),
});

const rpcMethodItemSchema = z.object({
  value: z.string(),
  label: z.string(),
  namespace: z.string(),
  namespace_label: z.string(),
  risk: rpcMethodRiskSchema,
  risk_label: z.string(),
  deprecated: z.boolean(),
});

const rpcMethodProtocolGroupSchema = z.object({
  protocol: rpcMethodProtocolSchema,
  protocol_label: z.string(),
  sources: z.array(rpcMethodSourceSchema),
  methods: z.array(rpcMethodItemSchema),
});

const rpcMethodCatalogSchema = z.object({
  items: z.array(rpcMethodProtocolGroupSchema),
});

const envelope = <T extends z.ZodType>(data: T) =>
  z.object({ msg: z.string(), data });

export type RpcMethodSource = z.infer<typeof rpcMethodSourceSchema>;
export type RpcMethodItem = z.infer<typeof rpcMethodItemSchema>;
export type RpcMethodProtocolGroup = z.infer<
  typeof rpcMethodProtocolGroupSchema
>;
export type RpcMethodCatalog = z.infer<typeof rpcMethodCatalogSchema>;

export type ListRpcMethodsParams = {
  protocol?: RpcMethodProtocol;
};

function buildListParams(input: ListRpcMethodsParams): Record<string, string> {
  const params: Record<string, string> = {};
  if (input.protocol !== undefined) params.protocol = input.protocol;
  return params;
}

export async function listRpcMethods(
  input: ListRpcMethodsParams = {},
): Promise<RpcMethodCatalog> {
  const response = await api.get<unknown>("/v2/meta/jsonrpc-methods", {
    params: buildListParams(input),
  });
  return envelope(rpcMethodCatalogSchema).parse(response).data;
}
