import { create } from "zustand";
import type { AuthIdentity } from "@/api/auth/client";

interface AuthState {
  authIdentity: AuthIdentity | null;
  setAuthIdentity: (identity: AuthIdentity | null) => void;
  clearAuthIdentity: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  authIdentity: null,
  setAuthIdentity: (identity) => set({ authIdentity: identity }),
  clearAuthIdentity: () => set({ authIdentity: null }),
}));
