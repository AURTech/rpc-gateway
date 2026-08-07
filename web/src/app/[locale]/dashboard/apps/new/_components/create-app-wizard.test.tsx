import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CreateAppWizard } from "./create-app-wizard";

const {
  createAppMock,
  listGatewaysMock,
  setAppProviderMock,
  syncProviderMock,
  updateGatewaysMock,
} = vi.hoisted(() => ({
  createAppMock: vi.fn(),
  listGatewaysMock: vi.fn(),
  setAppProviderMock: vi.fn(),
  syncProviderMock: vi.fn(),
  updateGatewaysMock: vi.fn(),
}));

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

vi.mock("@/hooks/use-apps", () => ({
  useCreateAppMutation: () => ({
    mutateAsync: createAppMock,
    isPending: false,
  }),
}));

vi.mock("@/hooks/use-gateways", () => ({
  useBulkUpdateGatewaysMutation: () => ({
    mutateAsync: updateGatewaysMock,
    isPending: false,
  }),
}));

vi.mock("@/api/gateways/client", () => ({
  listGateways: listGatewaysMock,
}));

vi.mock("@/api/apps/client", () => ({
  setAppProvider: setAppProviderMock,
}));

vi.mock("@/api/providers/client", () => ({
  syncProvider: syncProviderMock,
}));

vi.mock("@/i18n/navigation", async () =>
  (await import("@/test/navigation")).navigationMock(),
);

vi.mock("./rpc-access-step", () => ({
  RpcAccessStep: ({ onChange }: { onChange: (value: string) => void }) => (
    <div>
      RPC access form
      <button type="button" onClick={() => onChange("provider-1")}>
        Select provider
      </button>
    </div>
  ),
}));

describe("CreateAppWizard", () => {
  it("adds the optional RPC access step after network selection", async () => {
    const user = userEvent.setup();
    render(<CreateAppWizard />);

    expect(screen.getByText("steps.rpcAccess.short")).toBeInTheDocument();
    await user.type(
      screen.getByRole("textbox", { name: /form\.name/ }),
      "checkout",
    );
    await user.click(screen.getByRole("button", { name: "nav.next" }));

    await user.click(screen.getByRole("button", { name: "Ethereum" }));
    await user.click(screen.getByRole("button", { name: "nav.next" }));

    expect(screen.getByText("RPC access form")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "nav.skipCreate" }),
    ).toBeEnabled();
    expect(
      screen.getByRole("button", { name: "nav.createConnect" }),
    ).toBeDisabled();
  });

  it("creates the App without upstream resources when RPC access is skipped", async () => {
    const user = userEvent.setup();
    createAppMock.mockResolvedValue({ id: "app-1", name: "checkout" });
    listGatewaysMock.mockResolvedValue({
      page: 1,
      size: 50,
      total: 0,
      max_page: 0,
      items: [],
    });
    render(<CreateAppWizard />);

    await user.type(
      screen.getByRole("textbox", { name: /form\.name/ }),
      "checkout",
    );
    await user.click(screen.getByRole("button", { name: "nav.next" }));
    await user.click(screen.getByRole("button", { name: "Ethereum" }));
    await user.click(screen.getByRole("button", { name: "nav.next" }));
    await user.click(screen.getByRole("button", { name: "nav.skipCreate" }));

    await waitFor(() => {
      expect(screen.getByText("summary.skipped")).toBeInTheDocument();
    });
    expect(createAppMock).toHaveBeenCalledOnce();
    expect(listGatewaysMock).toHaveBeenCalledOnce();
    expect(updateGatewaysMock).not.toHaveBeenCalled();
  });

  it("associates and syncs an existing Provider without editing routes", async () => {
    const user = userEvent.setup();
    createAppMock.mockResolvedValue({ id: "app-1", name: "checkout" });
    listGatewaysMock.mockResolvedValue({
      page: 1,
      size: 50,
      total: 0,
      max_page: 0,
      items: [],
    });
    setAppProviderMock.mockResolvedValue({ app_id: "app-1" });
    syncProviderMock.mockResolvedValue({
      provider_id: "provider-1",
      status: "success",
      status_label: "Success",
    });
    render(<CreateAppWizard />);

    await user.type(
      screen.getByRole("textbox", { name: /form\.name/ }),
      "checkout",
    );
    await user.click(screen.getByRole("button", { name: "nav.next" }));
    await user.click(screen.getByRole("button", { name: "Ethereum" }));
    await user.click(screen.getByRole("button", { name: "nav.next" }));
    await user.click(screen.getByRole("button", { name: "Select provider" }));
    await user.click(screen.getByRole("button", { name: "nav.createConnect" }));

    await waitFor(() => {
      expect(screen.getByText("summary.providerConnected")).toBeInTheDocument();
    });
    expect(setAppProviderMock).toHaveBeenCalledWith("app-1", "provider-1");
    expect(syncProviderMock).toHaveBeenCalledWith("provider-1");
  });
});
