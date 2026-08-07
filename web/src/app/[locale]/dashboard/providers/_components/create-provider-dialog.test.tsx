import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createProvider } from "@/api/providers/client";
import { makeProviderDetail } from "@/test/fixtures";
import { createTestQueryClient, renderWithQuery } from "@/test/query";

import { CreateProviderDialog } from "./create-provider-dialog";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

vi.mock("@/api/providers/client", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/api/providers/client")>();
  return {
    ...actual,
    createProvider: vi.fn(),
  };
});

const createProviderMock = vi.mocked(createProvider);

afterEach(() => {
  vi.clearAllMocks();
});

describe("CreateProviderDialog", () => {
  it("hides Enabled and always creates an enabled provider", async () => {
    const user = userEvent.setup();
    const queryClient = createTestQueryClient();
    const onOpenChange = vi.fn();
    createProviderMock.mockResolvedValue(
      makeProviderDetail({ sync_enabled: false }),
    );

    renderWithQuery(
      <CreateProviderDialog open onOpenChange={onOpenChange} />,
      queryClient,
    );

    expect(
      screen.queryByRole("switch", { name: "form.enabled" }),
    ).not.toBeInTheDocument();

    await user.type(
      screen.getByRole("textbox", { name: /form\.name/ }),
      "alchemy-main",
    );
    await user.type(
      screen.getByRole("textbox", { name: /form\.secret/ }),
      "provider-secret",
    );
    await user.click(
      screen.getByRole("button", { name: "dialog.create.submit" }),
    );

    await waitFor(() => {
      expect(createProviderMock).toHaveBeenCalledWith({
        name: "alchemy-main",
        vendor: "alchemy",
        enabled: true,
        sync_enabled: false,
        credential: { secret: "provider-secret" },
        only_networks: undefined,
        ignore_networks: undefined,
      });
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });
});
