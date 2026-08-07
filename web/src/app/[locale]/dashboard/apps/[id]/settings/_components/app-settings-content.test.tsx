import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AppSettingsContent } from "./app-settings-content";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

vi.mock("sonner", async () => (await import("@/test/mocks")).sonnerMock());

vi.mock("@/hooks/use-apps", () => {
  const app = {
    id: "app-1",
    name: "production",
    enabled: true,
    version: 1,
    created_at: "2026-06-01T00:00:00Z",
    modified_at: "2026-06-01T00:00:00Z",
  };

  return {
    useAppQuery: () => ({
      data: app,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    }),
    useUpdateAppMutation: () => ({ isPending: false, mutate: vi.fn() }),
  };
});

vi.mock("./app-key-management", () => ({
  AppKeyManagement: () => <section data-testid="access-keys" />,
}));

vi.mock("./delete-app-dialog", () => ({
  DeleteAppDialog: () => null,
}));

describe("AppSettingsContent", () => {
  it("groups app settings and reveals the final save action after changes", async () => {
    const user = userEvent.setup();
    const { container } = render(<AppSettingsContent appId="app-1" />);

    const contentArea = container.querySelector(
      '[data-slot="app-settings-content-area"]',
    );
    expect(contentArea).toBeInstanceOf(HTMLElement);
    if (!(contentArea instanceof HTMLElement)) {
      throw new Error("App settings content area is required");
    }

    expect(
      within(contentArea).queryByRole("heading", {
        name: "settings.details.title",
      }),
    ).not.toBeInTheDocument();
    expect(
      within(contentArea).queryByText("settings.details.meta"),
    ).not.toBeInTheDocument();
    expect(within(contentArea).getByTestId("access-keys")).toBeInTheDocument();

    expect(
      within(contentArea).queryByRole("button", {
        name: "settings.details.save",
      }),
    ).not.toBeInTheDocument();

    const dangerHeading = screen.getByRole("heading", {
      name: "settings.danger.title",
    });
    const stateActions = container.querySelector(
      '[data-slot="app-state-actions"]',
    );
    expect(stateActions).toBeInstanceOf(HTMLElement);
    if (!(stateActions instanceof HTMLElement)) {
      throw new Error("App state actions block is required");
    }

    const enabledSwitch = within(stateActions).getByRole("switch", {
      name: "form.enabled",
    });
    expect(stateActions).toContainElement(dangerHeading);
    expect(enabledSwitch.compareDocumentPosition(dangerHeading)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );

    expect(
      within(stateActions).getByRole("button", {
        name: "settings.danger.delete",
      }),
    ).toHaveAttribute("data-variant", "destructive");

    const nameInput = screen.getByRole("textbox", { name: "form.name" });
    await user.clear(nameInput);

    const saveButton = within(contentArea).getByRole("button", {
      name: "settings.details.save",
    });
    expect(saveButton).toBeDisabled();

    await user.type(nameInput, "staging");
    expect(saveButton).toBeEnabled();
    expect(saveButton).toHaveAttribute("form", "app-settings-details-form");
    expect(contentArea.lastElementChild).toContainElement(saveButton);
    expect(stateActions.compareDocumentPosition(saveButton)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });
});
