"use client";

import { useEffect, useState } from "react";

import { usePathname, useRouter } from "@/i18n/navigation";

export type AppOverviewTab = "setup" | "gateways";

// One key holds every app the user has already opened, so the store stays a
// single entry instead of growing one key per app.
const STORAGE_KEY = "rpc-gateway:app-overview-visited";

function readVisited(): string[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed)
      ? parsed.filter((id): id is string => typeof id === "string")
      : [];
  } catch {
    // localStorage may be unavailable (SSR, private mode) or hold a value an
    // older build wrote — treat anything unreadable as "never visited".
    return [];
  }
}

function markVisited(appId: string) {
  try {
    const visited = readVisited();
    if (visited.includes(appId)) return;
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([...visited, appId]),
    );
  } catch {
    // ignore
  }
}

/**
 * Owns which Overview tab is showing, resolved in three layers:
 *
 *   1. `?tab=` on the URL — a deep link or a reload always wins.
 *   2. Whether this app has been opened before (per-app, in localStorage).
 *   3. Otherwise: first visit lands on "setup" to walk the user through their
 *      first request; every later visit lands on "gateways".
 *
 * localStorage can't be read while rendering without risking a hydration
 * mismatch, so the first paint follows the URL (defaulting to "setup") and the
 * effect below corrects it after mount — the same read-in-`useEffect` shape
 * `useSidebarPinned` uses. Opening the app is what marks it visited, so the
 * flip to "gateways" happens on the *next* visit rather than moments after this
 * one starts.
 */
export function useAppOverviewTab({
  appId,
  initialTab,
}: {
  appId: string;
  /** `?tab=` from the server, or undefined when the URL didn't specify one. */
  initialTab?: AppOverviewTab;
}) {
  const router = useRouter();
  const pathname = usePathname();

  const [tab, setTab] = useState<AppOverviewTab>(initialTab ?? "setup");

  useEffect(() => {
    const seen = readVisited().includes(appId);
    // The URL is explicit intent; only fall back to the visit history when it
    // stayed silent.
    if (initialTab) setTab(initialTab);
    else if (seen) setTab("gateways");
    markVisited(appId);
  }, [appId, initialTab]);

  const changeTab = (next: AppOverviewTab) => {
    setTab(next);
    // Mirror the tab into the URL so reloads and shared links keep it, matching
    // how the Endpoints page persists its own tab.
    router.replace(`${pathname}?tab=${next}`);
  };

  return { tab, changeTab };
}
