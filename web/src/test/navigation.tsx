import type { ComponentProps } from "react";
import { vi } from "vitest";

interface NavigationMockOptions {
  /** What `usePathname()` reports. */
  pathname?: string;
  /** Router spies a test wants to assert on; must come from `vi.hoisted`. */
  replace?: (href: string) => void;
  push?: (href: string) => void;
}

/**
 * Module factory for `vi.mock("@/i18n/navigation", …)`. The real module pulls
 * in `next-intl/navigation` → `next/navigation`, which vitest's jsdom
 * environment can't resolve, so every test rendering a link or router call
 * needs it stubbed:
 *
 * ```ts
 * vi.mock("@/i18n/navigation", async () =>
 *   (await import("@/test/navigation")).navigationMock(),
 * );
 * ```
 *
 * To assert a redirect, hand in a hoisted spy — a plain module-scope `vi.fn()`
 * is still in its temporal dead zone when the factory runs:
 *
 * ```ts
 * const { replaceMock } = vi.hoisted(() => ({ replaceMock: vi.fn() }));
 * vi.mock("@/i18n/navigation", async () =>
 *   (await import("@/test/navigation")).navigationMock({ replace: replaceMock }),
 * );
 * ```
 */
export function navigationMock({
  pathname = "/",
  replace = vi.fn(),
  push = vi.fn(),
}: NavigationMockOptions = {}) {
  function Link({
    href,
    children,
    onNavigate,
    onClick,
    ...props
  }: ComponentProps<"a"> & { onNavigate?: () => void }) {
    return (
      <a
        {...props}
        href={String(href)}
        onClick={(event) => {
          // jsdom implements no navigation, so keep the click inert: `href`
          // stays assertable and next-intl's `onNavigate` still fires.
          event.preventDefault();
          onClick?.(event);
          onNavigate?.();
        }}
      >
        {children}
      </a>
    );
  }

  return {
    Link,
    usePathname: () => pathname,
    useRouter: () => ({ replace, push }),
    redirect: vi.fn(),
  };
}
