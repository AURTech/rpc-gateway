import { screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { makeProvider } from "@/test/fixtures";
import { createTestQueryClient, renderWithQuery } from "@/test/query";

import { RpcAccessStep } from "./rpc-access-step";

const { listProvidersMock } = vi.hoisted(() => ({
  listProvidersMock: vi.fn(),
}));

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

vi.mock("@/hooks/use-is-admin", async () =>
  (await import("@/test/mocks")).useIsAdminMock(),
);

vi.mock("@/api/providers/client", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/api/providers/client")>();
  return { ...actual, listProviders: listProvidersMock };
});

function Harness() {
  const [value, setValue] = useState("");
  return <RpcAccessStep value={value} onChange={setValue} disabled={false} />;
}

function renderStep() {
  return renderWithQuery(<Harness />, createTestQueryClient());
}

function providerPage(items: unknown[]) {
  return { page: 1, size: 100, total: items.length, max_page: 1, items };
}

describe("RpcAccessStep", () => {
  beforeEach(() => {
    listProvidersMock.mockReset();
    listProvidersMock.mockResolvedValue(
      providerPage([
        makeProvider({
          id: "provider-1",
          account_id: "account-1",
          name: "Alchemy production",
          sync_enabled: false,
        }),
      ]),
    );
  });

  it("lists enabled account Providers next to the create dialog CTA", async () => {
    renderStep();

    await waitFor(() => expect(listProvidersMock).toHaveBeenCalledOnce());
    expect(
      screen.getByRole("combobox", { name: /provider.existingLabel/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "provider.createNew" }),
    ).toBeInTheDocument();
    // The inline provider form is gone — creating one goes through the dialog.
    expect(screen.queryByLabelText(/form.secret/)).not.toBeInTheDocument();
  });

  it("replaces the picker with an empty state when no Provider exists", async () => {
    listProvidersMock.mockResolvedValue(providerPage([]));
    renderStep();

    await waitFor(() =>
      expect(screen.getByText("provider.emptyTitle")).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: "provider.emptyCta" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });
});
