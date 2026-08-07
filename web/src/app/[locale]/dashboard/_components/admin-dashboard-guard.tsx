"use client";

import type { ReactNode } from "react";

import { useRequireAdmin } from "@/hooks/use-require-admin";

export function AdminDashboardGuard({ children }: { children: ReactNode }) {
  const query = useRequireAdmin();
  const isAdmin = query.data?.identity_type === "admin";

  if (!isAdmin) {
    return <div aria-busy="true" className="min-h-80 bg-page-bg" />;
  }

  return <>{children}</>;
}
