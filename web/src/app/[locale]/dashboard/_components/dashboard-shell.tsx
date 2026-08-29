"use client";

import { type ReactNode, useEffect, useMemo } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { useAppsQuery } from "@/hooks/use-apps";
import { useIsAdmin } from "@/hooks/use-is-admin";
import { useRequireAuth } from "@/hooks/use-require-auth";
import { usePathname, useRouter } from "@/i18n/navigation";
import {
  hasSeenAppOnboarding,
  markAppOnboardingSeen,
} from "@/lib/app-onboarding";
import { appIdFromPathname, buildDashboardNav } from "./nav-items";
import { UserIdentityBlock } from "./user-identity-block";

/**
 * App-specific wiring of the generic {@link AppShell}: feeds it this product's
 * navigation entries and account block. The shell itself stays free of these
 * details so it can be lifted into the template repo unchanged.
 */
export function DashboardShell({ children }: { children: ReactNode }) {
  // Verify the session is valid; bounces stale cookies back to /login.
  const auth = useRequireAuth();
  const apps = useAppsQuery({ size: 1 });
  const router = useRouter();

  // The admin experience now shares the regular dashboard; the only difference
  // is a small set of admin-only entries appended to the top-level sidebar.
  const { isAdmin } = useIsAdmin();
  const pathname = usePathname();
  const appId = appIdFromPathname(pathname);
  const navItems = useMemo(
    () => buildDashboardNav({ isAdmin, appId }),
    [isAdmin, appId],
  );

  useEffect(() => {
    const identity = auth.data;
    if (!apps.isSuccess || !identity) return;

    if (apps.data.total > 0) {
      markAppOnboardingSeen(identity);
    } else if (pathname === "/dashboard" && !hasSeenAppOnboarding(identity)) {
      markAppOnboardingSeen(identity);
      router.replace("/dashboard/apps/new");
    }
  }, [apps.data?.total, apps.isSuccess, auth.data, pathname, router]);

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
