"use client";

import { useAuthIdentity } from "@/hooks/use-auth";

/**
 * Role probe for shared `/dashboard/*` pages. Reads the cached identity from
 * {@link useAuthIdentity}; `isResolved` lets callers avoid role-sensitive UI
 * until the session subject has landed.
 */
export function useIsAdmin() {
  const { data, isPending } = useAuthIdentity();
  return {
    isAdmin: data?.identity_type === "admin",
    isResolved: !isPending && data !== undefined,
  };
}
