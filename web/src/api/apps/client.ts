import { z } from "zod/v4";

import { api } from "@/api/client";

const rpcAppBaseSchema = z.object({
  id: z.string(),
  name: z.string(),
  enabled: z.boolean(),
  provider_id: z.string().nullable().optional(),
  version: z.number().int().positive(),
  created_at: z.string(),
  modified_at: z.string(),
});

const rpcAppDetailSchema = rpcAppBaseSchema;

const createdRpcAppSchema = rpcAppDetailSchema.extend({
  api_key_id: z.string(),
  api_key: z.string(),
});

const rpcAppListItemSchema = rpcAppBaseSchema.extend({
  chains: z.array(z.string()),
  gateway_count: z.number().int().nonnegative(),
  enabled_gateway_count: z.number().int().nonnegative(),
});

const rpcAppListSchema = z.object({
  page: z.number().int(),
  size: z.number().int(),
  total: z.number().int(),
  max_page: z.number().int(),
  items: z.array(rpcAppListItemSchema),
});

const deletedRpcAppSchema = z.object({
  id: z.string(),
  version: z.number().int().positive(),
  deleted: z.boolean(),
});

const appProviderResultSchema = z.object({
  app_id: z.string(),
  provider: z
    .object({
      id: z.string(),
      name: z.string(),
      vendor: z.enum([
        "alchemy",
        "quicknode",
        "chainstack",
        "drpc",
        "tenderly",
      ]),
      vendor_label: z.string(),
    })
    .nullable(),
  route_targets_added: z.number().int().nonnegative(),
  route_targets_removed: z.number().int().nonnegative(),
  route_targets_skipped: z.number().int().nonnegative(),
});

const rpcAppKeyStateSchema = z.enum(["active", "grace", "revoked", "expired"]);

const rpcAppKeySchema = z.object({
  id: z.string(),
  api_key: z.string(),
  state: rpcAppKeyStateSchema,
  expires_at: z.string().nullable(),
  revoked_at: z.string().nullable(),
  created_at: z.string(),
});

const createdRpcAppKeySchema = rpcAppKeySchema;
const rpcAppKeyListSchema = z.object({
  total: z.number().int(),
  items: z.array(rpcAppKeySchema),
});

const envelope = <T extends z.ZodType>(data: T) =>
  z.object({ msg: z.string(), data });

export type RpcAppBase = z.infer<typeof rpcAppBaseSchema>;
export type RpcAppDetail = z.infer<typeof rpcAppDetailSchema>;
export type CreatedRpcApp = z.infer<typeof createdRpcAppSchema>;
export type RpcAppListItem = z.infer<typeof rpcAppListItemSchema>;
export type RpcAppList = z.infer<typeof rpcAppListSchema>;
export type RpcAppDeleteResult = z.infer<typeof deletedRpcAppSchema>;
export type AppProviderResult = z.infer<typeof appProviderResultSchema>;
export type RpcAppKeyState = z.infer<typeof rpcAppKeyStateSchema>;
export type RpcAppKey = z.infer<typeof rpcAppKeySchema>;
export type CreatedRpcAppKey = z.infer<typeof createdRpcAppKeySchema>;
export type RpcAppKeyList = z.infer<typeof rpcAppKeyListSchema>;

export type ListAppsParams = {
  search?: string | null;
  enabled?: boolean;
  start_at?: string;
  end_at?: string;
  sort?: "ASC" | "DESC";
  page?: number;
  size?: number;
};

export type CreateRpcAppParams = { name: string; enabled?: boolean };
export type UpdateRpcAppParams = {
  expected_version: number;
  name?: string;
  enabled?: boolean;
};

function toListParams(input: ListAppsParams): Record<string, string> {
  const params: Record<string, string> = {};
  if (input.search) params.search = input.search;
  if (input.enabled !== undefined) params.enabled = String(input.enabled);
  if (input.start_at !== undefined) params.start_at = input.start_at;
  if (input.end_at !== undefined) params.end_at = input.end_at;
  if (input.sort !== undefined) params.sort = input.sort;
  if (input.page) params.page = String(input.page);
  if (input.size) params.size = String(input.size);
  return params;
}

const APPS_BASE = "/v2/apps";

export async function listApps(
  input: ListAppsParams = {},
): Promise<RpcAppList> {
  const response = await api.get<unknown>(APPS_BASE, {
    params: toListParams(input),
  });
  return envelope(rpcAppListSchema).parse(response).data;
}

export async function getApp(id: string): Promise<RpcAppDetail> {
  const response = await api.get<unknown>(`${APPS_BASE}/${id}`);
  return envelope(rpcAppDetailSchema).parse(response).data;
}

export async function createApp(
  input: CreateRpcAppParams,
): Promise<CreatedRpcApp> {
  const response = await api.post<unknown>(APPS_BASE, input, {
    cache: "no-store",
  });
  return envelope(createdRpcAppSchema).parse(response).data;
}

export async function updateApp(
  id: string,
  input: UpdateRpcAppParams,
): Promise<RpcAppDetail> {
  const response = await api.patch<unknown>(`${APPS_BASE}/${id}`, input);
  return envelope(rpcAppDetailSchema).parse(response).data;
}

export async function deleteApp(id: string): Promise<RpcAppDeleteResult> {
  const response = await api.delete<unknown>(`${APPS_BASE}/${id}`);
  return envelope(deletedRpcAppSchema).parse(response).data;
}

export async function setAppProvider(
  appId: string,
  providerId: string,
): Promise<AppProviderResult> {
  const response = await api.put<unknown>(
    `${APPS_BASE}/${appId}/provider`,
    { provider_id: providerId },
    { cache: "no-store" },
  );
  return envelope(appProviderResultSchema).parse(response).data;
}

export async function clearAppProvider(
  appId: string,
): Promise<AppProviderResult> {
  const response = await api.delete<unknown>(`${APPS_BASE}/${appId}/provider`);
  return envelope(appProviderResultSchema).parse(response).data;
}

export async function listAppKeys(appId: string): Promise<RpcAppKeyList> {
  const response = await api.get<unknown>(`${APPS_BASE}/${appId}/api-keys`, {
    cache: "no-store",
  });
  return envelope(rpcAppKeyListSchema).parse(response).data;
}

export async function rotateAppKey(appId: string): Promise<CreatedRpcAppKey> {
  const response = await api.post<unknown>(
    `${APPS_BASE}/${appId}/api-keys/rotate`,
    undefined,
    { cache: "no-store" },
  );
  return envelope(createdRpcAppKeySchema).parse(response).data;
}

export async function revokeAppKey(
  appId: string,
  keyId: string,
): Promise<RpcAppKey> {
  const response = await api.post<unknown>(
    `${APPS_BASE}/${appId}/api-keys/${keyId}/revoke`,
    undefined,
    { cache: "no-store" },
  );
  return envelope(rpcAppKeySchema).parse(response).data;
}
