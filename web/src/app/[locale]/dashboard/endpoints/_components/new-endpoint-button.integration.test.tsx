import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { NewEndpointButton } from "./new-endpoint-button";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

vi.mock("@/hooks/use-is-admin", async () =>
  (await import("@/test/mocks")).useIsAdminMock(),
);

vi.mock("@/hooks/use-endpoints", () => ({
  useEndpointQuery: () => ({ data: null, refetch: vi.fn() }),
  useCreateEndpointMutation: () => ({ isPending: false, mutate: vi.fn() }),
  useUpdateEndpointMutation: () => ({ isPending: false, mutate: vi.fn() }),
}));

describe("NewEndpointButton integration", () => {
  it("opens a modal dialog from the gateway routing form", async () => {
    const { container } = render(
      <form>
        <NewEndpointButton
          label="Create endpoint"
          initialChain="ethereum"
          initialNetwork="mainnet"
          initialProtocol="jsonrpc"
          presentation="dialog"
        />
      </form>,
    );

    await userEvent.click(
      screen.getByRole("button", { name: "Create endpoint" }),
    );

    expect(
      await screen.findByRole("dialog", { name: "form.createTitle" }),
    ).toBeVisible();
    expect(
      document.querySelector("[data-slot='dialog-content']"),
    ).not.toBeNull();
    expect(document.querySelector("[data-slot='sheet-content']")).toBeNull();
    expect(container.querySelector("form form")).toBeNull();
  });
});
