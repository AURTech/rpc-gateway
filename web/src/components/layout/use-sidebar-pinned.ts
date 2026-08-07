"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "rpc-gateway:sidebar-pinned";

export function useSidebarPinned() {
  const [pinned, setPinned] = useState(true);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored === "0") setPinned(false);
    } catch {
      // localStorage may be unavailable (SSR, private mode, etc.) — ignore
    }
  }, []);

  const toggle = () => {
    setPinned((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      } catch {
        // ignore
      }
      return next;
    });
  };

  return { pinned, toggle };
}
