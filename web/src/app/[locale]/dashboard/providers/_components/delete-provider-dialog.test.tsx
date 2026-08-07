import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeProvider } from "@/test/fixtures";
import { createTestQueryClient, renderWithQuery } from "@/test/query";

import { DeleteProviderDialog } from "./delete-provider-dialog";

const { deleteProviderMock } = vi.hoisted(() => ({
  deleteProviderMock: vi.fn(),
}));

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

vi.mock("sonner", async () => (await import("@/test/mocks")).sonnerMock());

vi.mock("@/api/providers/client", () => ({
  deleteProvider: deleteProviderMock,
}));

const provider = makeProvider();

afterEach(() => {
  vi.clearAllMocks();
});

describe("DeleteProviderDialog", () => {
  it("keeps endpoints by default and sends the optional delete choice", async () => {
    deleteProviderMock.mockResolvedValue({
      id: provider.id,
      version: 2,
      deleted: true,
      archived_endpoints: 1,
      retained_endpoints: 1,
      detached_endpoints: 2,
    });
    const queryClient = createTestQueryClient();
    const user = userEvent.setup();

    renderWithQuery(
      <DeleteProviderDialog provider={provider} open onOpenChange={() => {}} />,
      queryClient,
    );

    const checkbox = screen.getByRole("checkbox", {
      name: "dialog.delete.deleteEndpoints",
    });
    expect(checkbox).not.toBeChecked();

    await user.click(checkbox);
    await user.click(
      screen.getByRole("button", { name: "dialog.delete.confirm" }),
    );

    await waitFor(() =>
      expect(deleteProviderMock).toHaveBeenCalledWith(provider.id, {
        delete_unreferenced_endpoints: true,
      }),
    );
  });
});
