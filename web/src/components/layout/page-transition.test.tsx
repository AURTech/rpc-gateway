import { render, screen } from "@testing-library/react";
import { useEffect } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PageTransition } from "./page-transition";

// The real module pulls in next-intl/navigation → next/navigation, which
// vitest's jsdom environment can't resolve. A mutable ref (rather than
// `@/test/navigation`'s fixed pathname) lets a test move between routes.
const { pathname } = vi.hoisted(() => ({
  pathname: { current: "/dashboard" },
}));

vi.mock("@/i18n/navigation", () => ({
  usePathname: () => pathname.current,
}));

/** Counts mounts so a remount is observable, not just a re-render. */
function MountCounter({ onMount }: { onMount: () => void }) {
  useEffect(() => {
    onMount();
  }, [onMount]);
  return <p>page body</p>;
}

beforeEach(() => {
  pathname.current = "/dashboard";
});

describe("PageTransition", () => {
  it("renders its children under a page-transition slot", () => {
    const { container } = render(
      <PageTransition>
        <p>page body</p>
      </PageTransition>,
    );

    expect(screen.getByText("page body")).toBeInTheDocument();
    expect(
      container.querySelector('[data-slot="page-transition"]'),
    ).not.toBeNull();
  });

  it("remounts the page subtree when the route changes", () => {
    const onMount = vi.fn();
    const { rerender } = render(
      <PageTransition>
        <MountCounter onMount={onMount} />
      </PageTransition>,
    );
    expect(onMount).toHaveBeenCalledTimes(1);

    // Same element tree, different route: the key change must force a fresh
    // mount, otherwise Motion has no mount to run `initial → animate` on.
    pathname.current = "/dashboard/endpoints";
    rerender(
      <PageTransition>
        <MountCounter onMount={onMount} />
      </PageTransition>,
    );

    expect(onMount).toHaveBeenCalledTimes(2);
  });

  it("keeps the subtree mounted when the route is unchanged", () => {
    const onMount = vi.fn();
    const { rerender } = render(
      <PageTransition>
        <MountCounter onMount={onMount} />
      </PageTransition>,
    );

    rerender(
      <PageTransition>
        <MountCounter onMount={onMount} />
      </PageTransition>,
    );

    expect(onMount).toHaveBeenCalledTimes(1);
  });
});
