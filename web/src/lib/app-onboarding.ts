import type { AuthIdentity } from "@/api/auth/client";

const STORAGE_PREFIX = "rpc-gateway:app-onboarding-seen:v1";
const seenAccounts = new Set<string>();

function accountKey(identity: AuthIdentity): string {
  return `${identity.identity_type}:${identity.id}`;
}

function storageKey(identity: AuthIdentity): string {
  return `${STORAGE_PREFIX}:${accountKey(identity)}`;
}

export function hasSeenAppOnboarding(identity: AuthIdentity): boolean {
  const key = accountKey(identity);
  if (seenAccounts.has(key)) return true;
  if (typeof window === "undefined") return false;

  try {
    const hasSeen = window.localStorage.getItem(storageKey(identity)) === "1";
    if (hasSeen) seenAccounts.add(key);
    return hasSeen;
  } catch {
    return false;
  }
}

export function markAppOnboardingSeen(identity: AuthIdentity): void {
  seenAccounts.add(accountKey(identity));
  if (typeof window === "undefined") return;

  try {
    window.localStorage.setItem(storageKey(identity), "1");
  } catch {
    // The in-memory marker still prevents repeat redirects in this session.
  }
}
