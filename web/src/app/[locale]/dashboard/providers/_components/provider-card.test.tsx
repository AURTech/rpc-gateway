import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RpcProviderBase } from "@/api/providers/client";
import { makeProvider } from "@/test/fixtures";
import { createTestQueryClient, renderWithQuery } from "@/test/query";

import { ProviderCard } from "./provider-card";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

// `@/i18n/navigation` pulls in next-intl/navigation → `next/navigation`, which
// vitest's jsdom env can't resolve.
vi.mock("@/i18n/navigation", async () =>
  (await import("@/test/navigation")).navigationMock(),
);

function renderCard(overrides: Partial<RpcProviderBase> = {}) {
  const queryClient = createTestQueryClient();
  const user = userEvent.setup();
  const onOpen = vi.fn();
  // A provider that has synced at least once, which is what the card's status
  // line is written for.
  const provider = makeProvider({
    last_sync_at: "2026-06-01T00:00:00Z",
    last_sync_status: "success",
    last_sync_status_label: "Success",
    last_sync_created: 1,
    last_sync_updated: 2,
    ...overrides,
  });
  const view = renderWithQuery(
    <ProviderCard provider={provider} onOpen={onOpen} />,
    queryClient,
  );
  return { user, onOpen, ...view };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("ProviderCard", () => {
  it("renders the vendor name and brand avatar", () => {
    renderCard();

    expect(screen.getByText("alchemy-main")).toBeInTheDocument();
    // jsdom never fires the Avatar image load, so the brand monogram fallback
    // ("A") stands in — this asserts the avatar is wired, image or fallback.
    expect(screen.getByText("A")).toBeInTheDocument();
  });

  it("surfaces product metadata from settings as chips", () => {
    renderCard({
      settings: {
        type: "Node & API",
        project: "mainnet-prod",
        tag_labels: ["primary", "eu"],
      },
    });

    expect(screen.getByText("Node & API")).toBeInTheDocument();
    expect(screen.getByText("mainnet-prod")).toBeInTheDocument();
    expect(screen.getByText("primary")).toBeInTheDocument();
    expect(screen.getByText("eu")).toBeInTheDocument();
  });

  it("folds tags beyond the cap into a +N chip", () => {
    renderCard({
      settings: { tag_labels: ["a", "b", "c", "d", "e"] },
    });

    // First three tags render; the remaining two collapse into the overflow.
    expect(screen.getByText("a")).toBeInTheDocument();
    expect(screen.getByText("c")).toBeInTheDocument();
    expect(screen.queryByText("d")).not.toBeInTheDocument();
    expect(screen.getByText("card.tagsMore")).toBeInTheDocument();
  });

  it("opens the detail drawer when the card is activated", async () => {
    const { user, onOpen } = renderCard();

    await user.click(
      screen.getByRole("button", { name: "actions.viewDetails" }),
    );

    // The card no longer navigates: it hands its id to the list, which opens
    // the drawer beside the grid.
    expect(onOpen).toHaveBeenCalledWith("prov_1");
  });

  it("exposes a single inline sync button and no overflow menu", () => {
    renderCard();

    // The card's one action is Sync; the overflow "⋯" menu (view/edit/toggle/
    // delete — all still reachable in the detail drawer) was dropped.
    expect(
      screen.getByRole("button", { name: "actions.syncNow" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "actions.openMenu" }),
    ).not.toBeInTheDocument();
  });

  it("does not open detail when the sync button is activated", async () => {
    const { user, onOpen } = renderCard();

    await user.click(screen.getByRole("button", { name: "actions.syncNow" }));

    // The button stops propagation so the card's row-level open handler stays put.
    expect(onOpen).not.toHaveBeenCalled();
  });
});
