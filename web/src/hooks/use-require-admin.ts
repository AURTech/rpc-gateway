"use client";

import { useEffect } from "react";

import { useAuthIdentity } from "@/hooks/use-auth";
import { useRouter } from "@/i18n/navigation";

/**
 * Client-side gate for admin-only dashboard pages. Builds on {@link useAuthIdentity}:
 * a missing/stale session bounces to /login (same as {@link useRequireAuth}),
 * and an authenticated-but-non-admin identity is sent back to the regular
 * dashboard. Server-side account routes enforce the same rule.
 */
export function useRequireAdmin() {
  const router = useRouter();
  const query = useAuthIdentity();
  const identity = query.data;

  useEffect(() => {
    if (query.isError) {
      router.replace("/login");
    } else if (identity && identity.identity_type !== "admin") {
      router.replace("/dashboard");
    }
  }, [query.isError, identity, router]);

  return query;
}
