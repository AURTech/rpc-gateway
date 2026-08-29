"use client";

import { useEffect, useRef } from "react";

/**
 * Allows the first settled table dataset to opt into per-row entrance motion.
 * The ref changes after commit without scheduling a render, so it cannot cancel
 * the CSS animations that just started. Later pagination/filter datasets render
 * without the stagger and rely on the table body's continuity fade instead.
 */
export function useInitialTableRowEntrance(ready: boolean): boolean {
  const hasPresented = useRef(false);
  const shouldAnimate = ready && !hasPresented.current;

  useEffect(() => {
    if (ready) hasPresented.current = true;
  }, [ready]);

  return shouldAnimate;
}
