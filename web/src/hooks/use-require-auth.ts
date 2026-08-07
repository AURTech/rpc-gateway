"use client";

import { useEffect } from "react";

import { useAuthIdentity } from "@/hooks/use-auth";
import { useRouter } from "@/i18n/navigation";

/**
 * Client-side gate for authenticated areas. The middleware only checks for the
 * presence of the session cookie; this verifies it's actually valid via
 * GET /v2/auth/me and redirects stale/expired sessions back to /login.
 */
export function useRequireAuth() {
  const router = useRouter();
  const query = useAuthIdentity();

  useEffect(() => {
    if (query.isError) {
      router.replace("/login");
    }
  }, [query.isError, router]);

  return query;
}
