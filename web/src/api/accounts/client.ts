import { z } from "zod/v4";

import { api } from "@/api/client";

/**
 * Admin-only account-management API. Auth rides on the session cookie
 * (`credentials: "include"` in the shared client).
 */

export const ACCOUNT_STATUSES = ["active", "disabled", "archived"] as const;
export type AccountStatus = (typeof ACCOUNT_STATUSES)[number];

export const ACCOUNT_ROLES = ["admin", "user"] as const;

/** Statuses an admin may set directly (the others are lifecycle-managed). */
export const UPDATABLE_ACCOUNT_STATUSES = ["active", "disabled"] as const;
export type UpdatableAccountStatus =
  (typeof UPDATABLE_ACCOUNT_STATUSES)[number];

const accountStatusSchema = z.enum(ACCOUNT_STATUSES);
const accountRoleSchema = z.enum(ACCOUNT_ROLES);

const accountBaseSchema = z.object({
  id: z.string(),
  email: z.string(),
  role: accountRoleSchema,
  status: accountStatusSchema,
  /** False until the account completes its own first sign-in. */
  activated: z.boolean(),
  name: z.string().nullable().optional(),
  avatar_url: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  modified_at: z.string().nullable().optional(),
  role_label: z.string(),
  status_label: z.string(),
});

const accountDetailSchema = accountBaseSchema.extend({
  first_login_at: z.string().nullable().optional(),
  last_login_at: z.string().nullable().optional(),
  last_login_ip: z.string().nullable().optional(),
  last_login_user_agent: z.string().nullable().optional(),
  gateway_count: z.number(),
  app_count: z.number(),
});

const accountListSchema = z.object({
  page: z.number(),
  size: z.number(),
  total: z.number(),
  max_page: z.number(),
  items: z.array(accountBaseSchema),
});

const accountArchiveResultSchema = z.object({
  total: z.number().int(),
  items: z.array(accountBaseSchema),
});

const envelope = <T extends z.ZodType>(data: T) =>
  z.object({ msg: z.string(), data });

export type AccountBase = z.infer<typeof accountBaseSchema>;
export type AccountDetail = z.infer<typeof accountDetailSchema>;
export type AccountList = z.infer<typeof accountListSchema>;

export type ListAccountsParams = {
  search?: string | null;
  status?: AccountStatus | null;
  activated?: boolean | null;
  /** Lower bound on `created_at`, inclusive; ISO 8601 with timezone. */
  start_at?: string;
  /** Upper bound on `created_at`, exclusive; ISO 8601 with timezone. */
  end_at?: string;
  /** `created_at` sort direction. Server default `DESC`. */
  sort?: "ASC" | "DESC";
  page?: number;
  size?: number;
};

export type CreateAccountParams = {
  email: string;
};

export type UpdateAccountStatusParams = {
  status: UpdatableAccountStatus;
};

function buildListParams(input: ListAccountsParams): Record<string, string> {
  const params: Record<string, string> = {};
  if (input.search) params.search = input.search;
  if (input.status) params.status = input.status;
  if (input.activated !== null && input.activated !== undefined) {
    params.activated = String(input.activated);
  }
  if (input.start_at !== undefined) params.start_at = input.start_at;
  if (input.end_at !== undefined) params.end_at = input.end_at;
  if (input.sort !== undefined) params.sort = input.sort;
  if (input.page) params.page = String(input.page);
  if (input.size) params.size = String(input.size);
  return params;
}

export async function listAccounts(
  input: ListAccountsParams = {},
): Promise<AccountList> {
  const response = await api.get<unknown>("/v2/accounts", {
    params: buildListParams(input),
  });
  return envelope(accountListSchema).parse(response).data;
}

export async function getAccount(id: string): Promise<AccountDetail> {
  const response = await api.get<unknown>(`/v2/accounts/${id}`);
  return envelope(accountDetailSchema).parse(response).data;
}

export async function createAccount(
  input: CreateAccountParams,
): Promise<AccountBase> {
  const response = await api.post<unknown>("/v2/accounts", input);
  return envelope(accountBaseSchema).parse(response).data;
}

export async function updateAccountStatus(
  id: string,
  input: UpdateAccountStatusParams,
): Promise<AccountBase> {
  const response = await api.post<unknown>(`/v2/accounts/${id}`, input);
  return envelope(accountBaseSchema).parse(response).data;
}

export async function archiveAccount(id: string): Promise<AccountBase> {
  const response = await api.post<unknown>("/v2/accounts/delete", {
    ids: [id],
  });
  return envelope(accountArchiveResultSchema).parse(response).data.items[0];
}
