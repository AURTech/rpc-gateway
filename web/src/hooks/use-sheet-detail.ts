"use client";

import { useCallback, useState } from "react";

/**
 * Side-Sheet detail pattern for list views. Owns the single-selection state
 * that drives a {@link DetailDrawer}, the selected-row highlight, and the
 * open/close wiring.
 *
 * Deliberately exposes NO row-click opener: detail opens only via an explicit
 * affordance — the row/card action menu's "View details" calling `toggle` — so
 * a side-Sheet list never opens on a stray row click. (Contrast the inline
 * row-expansion pattern, where the whole row is the toggle.)
 *
 * Generic over the item type; `selected` resolves against `items` so it
 * auto-clears when the row leaves the view (search / filter / page change).
 */
export function useSheetDetail<T>(
  items: readonly T[],
  getId: (item: T) => string,
) {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selected = items.find((item) => getId(item) === selectedId) ?? null;

  const toggle = useCallback(
    (id: string) => setSelectedId((prev) => (prev === id ? null : id)),
    [],
  );
  const close = useCallback(() => setSelectedId(null), []);
  const isSelected = useCallback(
    (id: string) => selectedId === id,
    [selectedId],
  );
  const onOpenChange = useCallback((next: boolean) => {
    if (!next) setSelectedId(null);
  }, []);

  return {
    /** Selected id, or null. */
    selectedId,
    /** Resolved selected item (null if none / left the view). */
    selected,
    /** Whether the drawer should be open. */
    open: selected !== null,
    isSelected,
    /** Open the detail for `id` (or close it if already open) — for the menu. */
    toggle,
    /** Close the drawer. */
    close,
    /** Pass straight to `DetailDrawer`'s `onOpenChange`. */
    onOpenChange,
  };
}
