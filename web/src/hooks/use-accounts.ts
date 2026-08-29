import {
  keepPreviousData,
  type QueryKey,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  type AccountDetail,
  type AccountList,
  archiveAccount,
  type CreateAccountParams,
  createAccount,
  getAccount,
  type ListAccountsParams,
  listAccounts,
  type UpdateAccountStatusParams,
  updateAccountStatus,
} from "@/api/accounts/client";

const root = ["accounts"] as const;

export const accountsKeys = {
  all: root,
  lists: () => [...root, "list"] as const,
  list: (params: ListAccountsParams) =>
    [...root, "list", normalizeListParams(params)] as const,
  detail: (id: string) => [...root, "detail", id] as const,
};

function normalizeListParams(params: ListAccountsParams) {
  return {
    search: params.search ?? "",
    status: params.status ?? "",
    activated: params.activated ?? null,
    start_at: params.start_at ?? "",
    end_at: params.end_at ?? "",
    sort: params.sort ?? "DESC",
    page: params.page ?? 1,
    size: params.size ?? 10,
  };
}

export function useAccountsQuery(
  params: ListAccountsParams,
  options?: { enabled?: boolean },
) {
  return useQuery<AccountList>({
    queryKey: accountsKeys.list(params) as unknown as QueryKey,
    queryFn: () => listAccounts(params),
    placeholderData: keepPreviousData,
    staleTime: 15_000,
    enabled: options?.enabled,
  });
}

/** Infinite (scroll-loading) variant of {@link useAccountsQuery} for the mobile
 *  list. Keyed on the filters minus `page`; pages accumulate via `data.pages`. */
export function useAccountsInfiniteQuery(
  params: Omit<ListAccountsParams, "page">,
  options?: { enabled?: boolean },
) {
  return useInfiniteQuery({
    queryKey: [
      ...accountsKeys.lists(),
      "infinite",
      {
        search: params.search ?? "",
        status: params.status ?? "",
        activated: params.activated ?? null,
        size: params.size ?? 10,
      },
    ] as unknown as QueryKey,
    queryFn: ({ pageParam }) => listAccounts({ ...params, page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (last: AccountList) =>
      last.page < last.max_page ? last.page + 1 : undefined,
    staleTime: 15_000,
    enabled: options?.enabled,
  });
}

export function useAccountQuery(id: string | null) {
  return useQuery<AccountDetail>({
    queryKey: accountsKeys.detail(id ?? "") as unknown as QueryKey,
    queryFn: () => getAccount(id as string),
    enabled: id !== null && id.length > 0,
  });
}

function invalidateLists(qc: ReturnType<typeof useQueryClient>) {
  return qc.invalidateQueries({ queryKey: accountsKeys.lists() });
}

export function useCreateAccountMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateAccountParams) => createAccount(input),
    onSuccess: () => invalidateLists(qc),
  });
}

export function useUpdateAccountStatusMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      input,
    }: {
      id: string;
      input: UpdateAccountStatusParams;
    }) => updateAccountStatus(id, input),
    onSuccess: (data) => {
      invalidateLists(qc);
      qc.setQueryData(accountsKeys.detail(data.id), data);
    },
  });
}

export function useArchiveAccountMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => archiveAccount(id),
    onSuccess: () => invalidateLists(qc),
  });
}
