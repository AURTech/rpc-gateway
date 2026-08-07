import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createPersonalAccessToken,
  listPersonalAccessTokens,
  revokePersonalAccessToken,
} from "@/api/personal-access-tokens/client";

export const personalAccessTokensQueryKey = [
  "auth",
  "personal-access-tokens",
] as const;

export function usePersonalAccessTokens() {
  return useQuery({
    queryKey: personalAccessTokensQueryKey,
    queryFn: listPersonalAccessTokens,
  });
}

export function useCreatePersonalAccessToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createPersonalAccessToken,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: personalAccessTokensQueryKey }),
  });
}

export function useRevokePersonalAccessToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: revokePersonalAccessToken,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: personalAccessTokensQueryKey }),
  });
}
