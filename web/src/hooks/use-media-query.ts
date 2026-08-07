"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * SSR-safe media query hook. Backed by `useSyncExternalStore` so the real match
 * is read synchronously on the first client render — no post-mount flash where
 * breakpoint-driven UI (responsive table/list swap, drawer side) shows the
 * mobile variant for a frame before resolving. Returns `false` during
 * SSR/hydration so the server HTML matches, then settles to the true value.
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const mql = window.matchMedia(query);
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    },
    [query],
  );

  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(query).matches,
    () => false,
  );
}

/** True at the Tailwind `md` breakpoint (≥48rem) and up. */
export function useIsDesktop(): boolean {
  return useMediaQuery("(min-width: 48rem)");
}
