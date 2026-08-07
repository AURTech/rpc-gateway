import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { copyToClipboard } from "@/lib/clipboard";

import { AppKeyManagement } from "./app-key-management";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

vi.mock("sonner", async () => (await import("@/test/mocks")).sonnerMock());

vi.mock("@/lib/clipboard", async () =>
  (await import("@/test/mocks")).clipboardMock(),
);

vi.mock("@/hooks/use-apps", () => ({
  useAppKeysQuery: () => ({
    isPending: false,
    isError: false,
    refetch: vi.fn(),
    data: {
      total: 2,
      items: [
        {
          id: "key-active",
          api_key: "ak_active_visible",
          state: "active",
          expires_at: null,
          revoked_at: null,
          created_at: "2026-06-01T00:00:00Z",
        },
        {
          id: "key-revoked",
          api_key: "ak_revoked_visible",
          state: "revoked",
          expires_at: null,
          revoked_at: "2026-07-01T00:00:00Z",
          created_at: "2026-05-01T00:00:00Z",
        },
      ],
    },
  }),
  useRotateAppKeyMutation: () => ({ isPending: false, mutate: vi.fn() }),
  useRevokeAppKeyMutation: () => ({ isPending: false, mutate: vi.fn() }),
}));

describe("AppKeyManagement", () => {
  it("shows every key directly and copies without a reveal action", async () => {
    render(<AppKeyManagement appId="app-1" />);

    expect(screen.getByText("ak_active_visible")).toBeInTheDocument();
    expect(screen.getByText("ak_revoked_visible")).toBeInTheDocument();
    expect(screen.queryByText("key-active")).not.toBeInTheDocument();
    expect(screen.queryByText("key-revoked")).not.toBeInTheDocument();
    expect(screen.getByText("columns.apiKey")).toBeInTheDocument();
    expect(screen.queryByText("columns.prefix")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "reveal" })).toBeNull();

    const copyButtons = screen.getAllByRole("button", { name: "copy" });
    expect(copyButtons[0]).toHaveAttribute("data-size", "icon-sm");
    expect(copyButtons[0]).not.toHaveTextContent("copy");
    await userEvent.click(copyButtons[0]);
    expect(copyToClipboard).toHaveBeenCalledWith("ak_active_visible");
  });

  it("uses a routing-style table with the rotate action in its header", () => {
    const { container } = render(<AppKeyManagement appId="app-1" />);

    const section = container.querySelector('[data-slot="app-key-management"]');
    expect(section).not.toBeNull();
    const heading = screen.getByRole("heading", { name: "title" });
    const header = heading.closest("header");
    expect(header).not.toBeNull();
    if (!header) throw new Error("Access keys heading must be in its header");
    expect(within(header).getByRole("heading", { name: "title" })).toBe(
      heading,
    );
    expect(
      within(header).getByRole("button", { name: "rotate" }),
    ).toBeInTheDocument();
    expect(within(header).getByRole("button", { name: "rotate" })).toHaveClass(
      "rounded-xl",
    );
    expect(screen.getByRole("table", { name: "title" })).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3);
    expect(screen.queryByText("rotateAction.title")).not.toBeInTheDocument();
  });
});
