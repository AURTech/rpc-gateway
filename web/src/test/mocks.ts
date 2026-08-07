import { vi } from "vitest";

/**
 * Module factory for `vi.mock("sonner", …)`. Every level is a spy, so a test
 * asserts on the one it cares about via `vi.mocked(toast.error)` after
 * importing `toast` from "sonner" as usual:
 *
 * ```ts
 * vi.mock("sonner", async () => (await import("@/test/mocks")).sonnerMock());
 * ```
 *
 * `Toaster` is left out — it is mounted by the app shell, never by a component
 * under test.
 */
export function sonnerMock() {
  return {
    toast: {
      success: vi.fn(),
      warning: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
    },
  };
}

/**
 * Module factory for `vi.mock("@/lib/clipboard", …)`. jsdom has no clipboard
 * permission model, so copies resolve `true` and the test asserts on the text
 * that was handed over.
 */
export function clipboardMock() {
  return { copyToClipboard: vi.fn(async () => true) };
}

/**
 * Module factory for `vi.mock("@/hooks/use-is-admin", …)`. `isResolved` is true
 * so admin-gated controls settle immediately instead of rendering their
 * still-loading branch.
 */
export function useIsAdminMock({
  isAdmin = false,
}: {
  isAdmin?: boolean;
} = {}) {
  return { useIsAdmin: () => ({ isAdmin, isResolved: true }) };
}
