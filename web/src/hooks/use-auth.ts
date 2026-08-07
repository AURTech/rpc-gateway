import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { getAuthIdentity, logout } from "@/api/auth/client";
import { useAuthStore } from "@/stores/auth-store";

export const authIdentityQueryKey = ["auth", "me"] as const;

export function useAuthIdentity(options?: { enabled?: boolean }) {
  const setAuthIdentity = useAuthStore((state) => state.setAuthIdentity);
  const clearAuthIdentity = useAuthStore((state) => state.clearAuthIdentity);

  const query = useQuery({
    queryKey: authIdentityQueryKey,
    queryFn: getAuthIdentity,
    retry: false,
    staleTime: 60_000,
    enabled: options?.enabled ?? true,
  });

  useEffect(() => {
    if (query.data) {
      setAuthIdentity(query.data);
    }
  }, [query.data, setAuthIdentity]);

  useEffect(() => {
    if (query.isError) {
      clearAuthIdentity();
    }
  }, [clearAuthIdentity, query.isError]);

  return query;
}

export function useLogout() {
  const queryClient = useQueryClient();
  const clearAuthIdentity = useAuthStore((state) => state.clearAuthIdentity);

  return useMutation({
    mutationFn: logout,
    onSuccess: () => {
      clearAuthIdentity();
      queryClient.removeQueries();
    },
  });
}
