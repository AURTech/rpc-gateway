"use client";

import { type ReactNode, useMemo } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { useIsAdmin } from "@/hooks/use-is-admin";
import { useRequireAuth } from "@/hooks/use-require-auth";
import { usePathname } from "@/i18n/navigation";
import { appIdFromPathname, buildDashboardNav } from "./nav-items";
import { UserIdentityBlock } from "./user-identity-block";

/**
 * App-specific wiring of the generic {@link AppShell}: feeds it this product's
 * navigation entries and account block. The shell itself stays free of these
 * details so it can be lifted into the template repo unchanged.
 */
export function DashboardShell({ children }: { children: ReactNode }) {
  // Verify the session is valid; bounces stale cookies back to /login.
  useRequireAuth();

  // The admin experience now shares the regular dashboard; the only difference
  // is a small set of admin-only entries appended to the top-level sidebar.
  const { isAdmin } = useIsAdmin();
  const pathname = usePathname();
  const appId = appIdFromPathname(pathname);
  const navItems = useMemo(
    () => buildDashboardNav({ isAdmin, appId }),
    [isAdmin, appId],
  );

  return (
    <AppShell
      navItems={navItems}
      renderUserSlot={({ onOpenChange }) => (
        <UserIdentityBlock onOpenChange={onOpenChange} />
      )}
    >
      {children}
    </AppShell>
  );
}
