import { z } from "zod/v4";

import { api } from "@/api/client";

export const personalAccessTokenScopes = [
  "overview:read",
  "apps:read",
  "apps:write",
  "app-keys:read",
  "app-keys:write",
  "gateways:read",
  "gateways:write",
  "endpoints:read",
  "endpoints:write",
  "endpoint-secrets:read",
  "providers:read",
  "providers:write",
  "routes:read",
  "routes:write",
  "usage:read",
  "meta:read",
  "accounts:read",
  "accounts:write",
  "policies:read",
  "policies:write",
] as const;

export type PersonalAccessTokenScope =
  (typeof personalAccessTokenScopes)[number];

const tokenItemSchema = z.object({
  id: z.string(),
  name: z.string(),
  token_prefix: z.string(),
  scopes: z.array(z.enum(personalAccessTokenScopes)),
  state: z.enum(["active", "expired", "revoked"]),
  expires_at: z.string(),
  last_used_at: z.string().nullable(),
  revoked_at: z.string().nullable(),
  created_at: z.string(),
});

const tokenListSchema = z.object({
  page: z.number(),
  size: z.number(),
  total: z.number(),
  max_page: z.number(),
  active: z.number(),
  max_active: z.number(),
  items: z.array(tokenItemSchema),
});

const createdTokenSchema = tokenItemSchema.extend({ token: z.string() });
const revokedTokenSchema = z.object({
  id: z.string(),
  revoked: z.boolean(),
  revoked_at: z.string(),
});
const responseEnvelopeSchema = <T extends z.ZodType>(dataSchema: T) =>
  z.object({ msg: z.string(), data: dataSchema });

export type PersonalAccessToken = z.infer<typeof tokenItemSchema>;
export type CreatedPersonalAccessToken = z.infer<typeof createdTokenSchema>;

export async function listPersonalAccessTokens(): Promise<{
  items: PersonalAccessToken[];
  total: number;
  active: number;
  maxActive: number;
}> {
  const response = await api.get<unknown>("/v2/auth/personal-access-tokens", {
    params: { size: "20", state: "active" },
  });
  const data = responseEnvelopeSchema(tokenListSchema).parse(response).data;
  return {
    items: data.items,
    total: data.total,
    active: data.active,
    maxActive: data.max_active,
  };
}

export async function createPersonalAccessToken(input: {
  name: string;
  scopes: PersonalAccessTokenScope[];
  expires_at?: string;
}): Promise<CreatedPersonalAccessToken> {
  const response = await api.post<unknown>(
    "/v2/auth/personal-access-tokens",
    input,
  );
  return responseEnvelopeSchema(createdTokenSchema).parse(response).data;
}

export async function revokePersonalAccessToken(
  tokenId: string,
): Promise<void> {
  const response = await api.delete<unknown>(
    `/v2/auth/personal-access-tokens/${tokenId}`,
  );
  responseEnvelopeSchema(revokedTokenSchema).parse(response);
}
