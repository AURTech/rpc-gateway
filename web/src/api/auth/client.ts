import { z } from "zod/v4";
import { api } from "@/api/client";

const authIdentitySchema = z.object({
  identity_type: z.enum(["admin", "user"]),
  id: z.string(),
  email: z.email(),
  name: z.string().nullable().optional(),
  avatar_url: z.string().nullable().optional(),
});

const logoutResultSchema = z.object({
  logged_out: z.literal(true),
});

const loginResultSchema = z.object({
  identity_type: z.enum(["admin", "user"]),
  id: z.string(),
  email: z.email(),
  expires_at: z.string(),
});

const passwordResultSchema = z.object({
  updated: z.boolean(),
});

const responseEnvelopeSchema = <T extends z.ZodType>(dataSchema: T) =>
  z.object({
    msg: z.string(),
    data: dataSchema,
  });

export type AuthIdentity = z.infer<typeof authIdentitySchema>;

export async function getAuthIdentity(): Promise<AuthIdentity> {
  const response = await api.get<unknown>("/v2/auth/me");
  return responseEnvelopeSchema(authIdentitySchema).parse(response).data;
}

export async function passwordLogin(input: {
  email: string;
  password: string;
}): Promise<void> {
  const response = await api.post<unknown>("/v2/auth/login", input);
  responseEnvelopeSchema(loginResultSchema).parse(response);
}

export async function setPassword(input: {
  new_password: string;
  old_password?: string;
}): Promise<void> {
  const response = await api.post<unknown>("/v2/auth/password", input);
  responseEnvelopeSchema(passwordResultSchema).parse(response);
}

export async function logout(): Promise<void> {
  const response = await api.post<unknown>("/v2/auth/logout");
  responseEnvelopeSchema(logoutResultSchema).parse(response);
}
