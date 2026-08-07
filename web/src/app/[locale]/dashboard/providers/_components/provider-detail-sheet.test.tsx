import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getProvider,
  type RpcProvider,
  updateProvider,
} from "@/api/providers/client";
import { makeProviderDetail } from "@/test/fixtures";
import { createTestQueryClient, renderWithQuery } from "@/test/query";

import { ProviderDetailSheet } from "./provider-detail-sheet";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

vi.mock("@/i18n/navigation", async () =>
  (await import("@/test/navigation")).navigationMock(),
);

vi.mock("@/api/providers/client", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/api/providers/client")>();
  return {
    ...actual,
    getProvider: vi.fn(),
    updateProvider: vi.fn(),
  };
});

const getProviderMock = vi.mocked(getProvider);
const updateProviderMock = vi.mocked(updateProvider);

/** A provider that has synced once, which is what the sheet's summary reads. */
function makeProvider(overrides: Partial<RpcProvider> = {}): RpcProvider {
  return makeProviderDetail({
    last_sync_at: "2026-06-01T00:00:00Z",
    last_sync_status: "success",
    last_sync_status_label: "Success",
    last_sync_created: 3,
    last_sync_updated: 1,
    ...overrides,
  });
}

function renderSheet(onOpenChange = vi.fn()) {
  const queryClient = createTestQueryClient();
  renderWithQuery(
    <ProviderDetailSheet
      providerId="prov_1"
      open
      onOpenChange={onOpenChange}
    />,
    queryClient,
  );
  return { onOpenChange };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("ProviderDetailSheet", () => {
  it("waits for provider data before opening the sheet", async () => {
    let resolveProvider!: (provider: RpcProvider) => void;
    getProviderMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveProvider = resolve;
        }),
    );

    renderSheet();

    expect(screen.queryByText("detail.loading")).not.toBeInTheDocument();

    resolveProvider(makeProvider());

    expect(
      await screen.findByRole("textbox", { name: /form\.name/ }),
    ).toHaveValue("alchemy-main");
  });

  it("uses the standard single-column provider form and fixed form actions", async () => {
    getProviderMock.mockResolvedValue(makeProvider());

    renderSheet();

    expect(
      await screen.findByRole("heading", { name: "dialog.edit.title" }),
    ).toBeInTheDocument();
    expect(screen.getByText("dialog.edit.subtitle")).toBeInTheDocument();

    const name = await screen.findByRole("textbox", { name: /form\.name/ });
    const vendor = screen.getByRole("combobox", { name: "form.vendor" });
    const secret = screen.getByRole("textbox", { name: /form\.secret/ });
    const network = screen.getByRole("radiogroup", {
      name: "form.networkFilter",
    });
    const autoSync = screen.getByRole("switch", { name: "form.autoSync" });
    const enabled = screen.getByRole("switch", { name: "form.enabled" });

    expect(name).toHaveValue("alchemy-main");
    expect(vendor).toBeDisabled();
    expect(secret).toHaveValue("provider-secret");
    expect(screen.getByText("form.networkFilter")).toBeInTheDocument();

    const controls = [name, vendor, secret, autoSync, network, enabled];
    for (let index = 0; index < controls.length - 1; index += 1) {
      expect(
        controls[index]?.compareDocumentPosition(controls[index + 1] as Node) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    }

    const cancel = screen.getByRole("button", { name: "dialog.cancel" });
    const save = screen.getByRole("button", { name: "dialog.edit.submit" });
    expect(cancel).toBeInTheDocument();
    expect(save).toBeDisabled();
    expect(save).toHaveAttribute("form", "provider-edit-form");

    const deleteButton = screen.getByRole("button", {
      name: "actions.deleteProvider",
    });
    expect(deleteButton).toHaveAttribute("type", "button");
    expect(deleteButton).toHaveAttribute("data-variant", "destructive");
    expect(screen.getByText("detail.deleteTitle")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /actions\.syncNow/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("detail.endpointsCount")).not.toBeInTheDocument();
  });

  it("submits all edited fields through one footer save", async () => {
    const user = userEvent.setup();
    const updated = makeProvider({ name: "alchemy-prod", sync_enabled: false });
    getProviderMock.mockResolvedValue(makeProvider());
    updateProviderMock.mockResolvedValue(updated);
    const { onOpenChange } = renderSheet();

    const name = await screen.findByRole("textbox", { name: /form\.name/ });
    await user.clear(name);
    await user.type(name, "alchemy-prod");
    await user.click(screen.getByRole("switch", { name: "form.autoSync" }));

    expect(updateProviderMock).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", { name: "dialog.edit.submit" }),
    );

    await waitFor(() => {
      expect(updateProviderMock).toHaveBeenCalledTimes(1);
      expect(updateProviderMock).toHaveBeenCalledWith("prov_1", {
        expected_version: 1,
        name: "alchemy-prod",
        sync_enabled: false,
      });
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it("confirms credential replacement when the form is saved", async () => {
    const user = userEvent.setup();
    getProviderMock.mockResolvedValue(makeProvider());
    updateProviderMock.mockResolvedValue(
      makeProvider({ credential: { has_secret: true, secret: "new-secret" } }),
    );
    renderSheet();

    const secret = await screen.findByRole("textbox", {
      name: /form\.secret/,
    });
    await user.clear(secret);
    await user.type(secret, "new-secret");
    await user.click(
      screen.getByRole("button", { name: "dialog.edit.submit" }),
    );

    expect(updateProviderMock).not.toHaveBeenCalled();
    const dialog = screen
      .getByText("detail.secretReplaceTitle")
      .closest('[role="dialog"]');
    expect(dialog).not.toBeNull();
    await user.click(
      within(dialog as HTMLElement).getByRole("button", {
        name: "detail.secretReplaceConfirm",
      }),
    );

    await waitFor(() => {
      expect(updateProviderMock).toHaveBeenCalledWith("prov_1", {
        expected_version: 1,
        credential: { secret: "new-secret" },
      });
    });
  });

  it("confirms disabling only after the unified save is pressed", async () => {
    const user = userEvent.setup();
    getProviderMock.mockResolvedValue(makeProvider());
    updateProviderMock.mockResolvedValue(makeProvider({ enabled: false }));
    renderSheet();

    await screen.findByRole("textbox", { name: /form\.name/ });
    await user.click(screen.getByRole("switch", { name: "form.enabled" }));

    expect(screen.queryByText("detail.disableTitle")).not.toBeInTheDocument();
    expect(updateProviderMock).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", { name: "dialog.edit.submit" }),
    );

    const dialog = screen
      .getByText("detail.disableTitle")
      .closest('[role="dialog"]');
    expect(dialog).not.toBeNull();
    await user.click(
      within(dialog as HTMLElement).getByRole("button", {
        name: "actions.toggleOff",
      }),
    );

    await waitFor(() => {
      expect(updateProviderMock).toHaveBeenCalledWith("prov_1", {
        expected_version: 1,
        enabled: false,
      });
    });
  });

  it("uses one explicit confirmation when disabling and replacing the secret", async () => {
    const user = userEvent.setup();
    getProviderMock.mockResolvedValue(makeProvider());
    updateProviderMock.mockResolvedValue(
      makeProvider({
        enabled: false,
        credential: { has_secret: true, secret: "new-secret" },
      }),
    );
    renderSheet();

    const secret = await screen.findByRole("textbox", {
      name: /form\.secret/,
    });
    await user.clear(secret);
    await user.type(secret, "new-secret");
    await user.click(screen.getByRole("switch", { name: "form.enabled" }));
    await user.click(
      screen.getByRole("button", { name: "dialog.edit.submit" }),
    );

    const dialog = screen
      .getByText("detail.sensitiveChangesTitle")
      .closest('[role="dialog"]');
    expect(dialog).not.toBeNull();
    await user.click(
      within(dialog as HTMLElement).getByRole("button", {
        name: "dialog.edit.submit",
      }),
    );

    await waitFor(() => {
      expect(updateProviderMock).toHaveBeenCalledWith("prov_1", {
        expected_version: 1,
        credential: { secret: "new-secret" },
        enabled: false,
      });
    });
  });

  it("closes without saving from the footer cancel action", async () => {
    const user = userEvent.setup();
    getProviderMock.mockResolvedValue(makeProvider());
    const { onOpenChange } = renderSheet();

    await screen.findByRole("textbox", { name: /form\.name/ });
    await user.click(screen.getByRole("button", { name: "dialog.cancel" }));

    expect(updateProviderMock).not.toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("shows the not-found state when the provider fails to load", async () => {
    getProviderMock.mockRejectedValue(new Error("boom"));

    renderSheet();

    expect(await screen.findByText("detail.notFoundTitle")).toBeInTheDocument();
  });
});
