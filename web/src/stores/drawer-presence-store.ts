import { create } from "zustand";

/**
 * Tracks how many slide-out detail drawers are open so the app shell
 * can scale the background back (iOS-style sheet presentation) while any are
 * visible. Ref-counted to stay correct if drawers ever nest or overlap.
 */
interface DrawerPresenceState {
  openCount: number;
  open: () => void;
  close: () => void;
}

export const useDrawerPresenceStore = create<DrawerPresenceState>((set) => ({
  openCount: 0,
  open: () => set((s) => ({ openCount: s.openCount + 1 })),
  close: () => set((s) => ({ openCount: Math.max(0, s.openCount - 1) })),
}));
