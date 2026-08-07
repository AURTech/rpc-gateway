import { fireEvent, render, screen } from "@testing-library/react";
import type { Dispatch, SetStateAction } from "react";
import { describe, expect, it, vi } from "vitest";

import type { Endpoint } from "@/api/endpoints/client";

import { EndpointsView } from "./endpoints-view";

vi.mock("next-intl", async () =>
  (await import("@/test/intl")).nextIntlMock({ separator: ":" }),
);

vi.mock("@/i18n/navigation", async () =>
  (await import("@/test/navigation")).navigationMock({
    pathname: "/dashboard/endpoints",
  }),
);

vi.mock("./endpoints-content", () => ({
  EndpointsContent: ({
    origin,
    setSelectedById,
    bulkDeleteOpen,
  }: {
    origin: "manual" | "provider";
    setSelectedById: Dispatch<SetStateAction<Map<string, Endpoint>>>;
    bulkDeleteOpen: boolean;
  }) => (
    <div>
      content
      {origin === "manual" ? (
        <button
          type="button"
          onClick={() =>
            setSelectedById(
              new Map([["endpoint-1", {} as unknown as Endpoint]]),
            )
          }
        >
          select endpoint
        </button>
      ) : null}
      {bulkDeleteOpen ? <span>bulk dialog open</span> : null}
    </div>
  ),
}));

// The create sheet pulls in the whole endpoint form; the CTA button itself is
// the real shared Button, which is what the sizing assertions are about.
vi.mock("./edit-endpoint-sheet", () => ({
  EditEndpointSheet: () => null,
}));

vi.mock("@/hooks/use-is-admin", async () =>
  (await import("@/test/mocks")).useIsAdminMock(),
);

describe("EndpointsView", () => {
  it("does not reserve space for the manage-providers arrow while hidden", () => {
    render(<EndpointsView initialTab="provider" />);

    const link = screen.getByRole("link", { name: "cta.manageProviders" });
    const iconSlot = link.querySelector("span[aria-hidden='true']");

    expect(link).not.toHaveClass("gap-2");
    expect(iconSlot).toHaveClass(
      "w-0",
      "group-hover:ml-2",
      "group-hover:w-4",
      "group-focus-visible:ml-2",
      "group-focus-visible:w-4",
      "pointer-coarse:ml-2",
      "pointer-coarse:w-4",
    );
  });

  /** Both tabs use the same Button size in the page header. */
  it("renders both tabs' header CTAs via the shared Button at the same size", () => {
    const { unmount } = render(<EndpointsView initialTab="manual" />);
    const manual = screen.getByRole("button", { name: /cta.newEndpoint/ });

    expect(manual).toHaveAttribute("data-slot", "button");
    expect(manual.closest("header")).not.toBeNull();
    const manualSize = manual.getAttribute("data-size");
    expect(manualSize).toBe("xl");
    unmount();

    render(<EndpointsView initialTab="provider" />);
    const provider = screen.getByRole("link", { name: "cta.manageProviders" });

    expect(provider).toHaveAttribute("data-slot", "button");
    expect(provider.closest("header")).not.toBeNull();
    expect(provider.getAttribute("data-size")).toBe(manualSize);
  });

  it("keeps the provider CTA on the soft variant", () => {
    render(<EndpointsView initialTab="provider" />);

    expect(
      screen.getByRole("link", { name: "cta.manageProviders" }),
    ).toHaveAttribute("data-variant", "soft");
  });

  it("renders bulk deletion in the tab action slot and clears it on tab change", () => {
    const { container } = render(<EndpointsView initialTab="manual" />);
    const actionSlot = container.querySelector(
      '[data-slot="endpoint-tab-action"]',
    );
    const manual = screen.getByRole("button", { name: /cta.newEndpoint/ });

    expect(actionSlot).toHaveClass("flex", "w-48", "shrink-0", "justify-end");
    expect(actionSlot).toBeEmptyDOMElement();
    expect(manual.closest("header")).not.toBeNull();
    expect(
      screen.queryByRole("link", { name: "cta.manageProviders" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "select endpoint" }));
    const bulkDelete = screen.getByRole("button", {
      name: "bulk.deleteSelectedCount:1",
    });
    expect(actionSlot).toContainElement(bulkDelete);
    expect(bulkDelete).toHaveAttribute("data-size", "sm");
    fireEvent.click(bulkDelete);
    expect(screen.getByText("bulk dialog open")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "tabs.provider" }));

    expect(
      screen.queryByRole("button", { name: /cta.newEndpoint/ }),
    ).not.toBeInTheDocument();
    expect(actionSlot).toBeEmptyDOMElement();
    expect(screen.queryByText("bulk dialog open")).not.toBeInTheDocument();
    expect(
      screen
        .getByRole("link", { name: "cta.manageProviders" })
        .closest("header"),
    ).not.toBeNull();

    fireEvent.click(screen.getByRole("tab", { name: "tabs.manual" }));
    expect(actionSlot).toBeEmptyDOMElement();
  });
});
