import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/client";
import {
  bulkUpdateGateways,
  listGateways,
  type RpcGatewayBase,
} from "@/api/gateways/client";
import { copyToClipboard } from "@/lib/clipboard";
import { gatewayList, makeGateway as sharedGateway } from "@/test/fixtures";
import { createTestQueryClient, renderWithQuery } from "@/test/query";

import { AppNetworksPanel } from "./app-networks-panel";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

vi.mock("@/i18n/navigation", async () =>
  (await import("@/test/navigation")).navigationMock(),
);

vi.mock("sonner", async () => (await import("@/test/mocks")).sonnerMock());

vi.mock("@/lib/clipboard", async () =>
  (await import("@/test/mocks")).clipboardMock(),
);

vi.mock("@/api/gateways/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/gateways/client")>();
  return { ...actual, bulkUpdateGateways: vi.fn(), listGateways: vi.fn() };
});

const listGatewaysMock = vi.mocked(listGateways);
const bulkUpdateGatewaysMock = vi.mocked(bulkUpdateGateways);
const copyMock = vi.mocked(copyToClipboard);
const toastErrorMock = vi.mocked(toast.error);

/** A TRON gateway exposing both HTTP transports, which the panel switches between. */
function makeGateway(overrides: Partial<RpcGatewayBase> = {}): RpcGatewayBase {
  return sharedGateway({
    id: "gw_tron_mainnet",
    name: "tron-mainnet",
    chain: "tron",
    network: "mainnet",
    access_points: [
      {
        transport: "jsonrpc",
        url: "https://tron-jsonrpc.example.test/{path_key}",
      },
      {
        transport: "http_api",
        url: "https://tron-httpapi.example.test/{path_key}",
      },
    ],
    ...overrides,
  });
}

function renderPanel(appId = "app_1") {
  const client = createTestQueryClient();
  return renderWithQuery(
    <AppNetworksPanel
      appId={appId}
      pathKeyState={{
        pathKey: "pk_secret",
        status: "available",
        refetchKeys: vi.fn(),
        isRefetchingKeys: false,
      }}
    />,
    client,
  );
}

const copyButtons = () =>
  screen.getAllByRole("button", { name: "table.copyEndpoint" });

beforeEach(() => {
  sessionStorage.clear();
  listGatewaysMock.mockImplementation(async () => gatewayList([makeGateway()]));
  bulkUpdateGatewaysMock.mockImplementation(async (_appId, input) => ({
    total: input.gateways.length,
    items: input.gateways.map((target) =>
      makeGateway({
        id: target.id,
        enabled: input.enabled,
        effective_enabled: input.enabled,
        version: target.expected_version + 1,
      }),
    ),
  }));
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("AppNetworksPanel", () => {
  it("renders the default protocol's access point with the visible path key filled in", async () => {
    renderPanel();

    // The chain card defaults to JSON-RPC; the HTTP API URL is reachable via the
    // endpoint-column protocol selector, not rendered up front.
    expect(
      await screen.findByText("https://tron-jsonrpc.example.test/pk_secret"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("https://tron-httpapi.example.test/pk_secret"),
    ).not.toBeInTheDocument();
    expect(copyButtons()).toHaveLength(1);
  });

  it("places the protocol picker in the endpoint column and switches its rows", async () => {
    renderPanel();

    const chainHeading = await screen.findByRole("heading", { name: "TRON" });
    const cardHeader = chainHeading.closest("header");
    expect(cardHeader).not.toBeNull();
    expect(
      within(cardHeader as HTMLElement).queryByRole("button"),
    ).not.toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "transport.jsonrpc" }),
    );
    await userEvent.click(
      screen.getByRole("menuitemradio", { name: "transport.http_api" }),
    );

    expect(
      await screen.findByText("https://tron-httpapi.example.test/pk_secret"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("https://tron-jsonrpc.example.test/pk_secret"),
    ).not.toBeInTheDocument();
  });

  it("copies the visible endpoint through the panel handler", async () => {
    renderPanel();

    await screen.findByText("https://tron-jsonrpc.example.test/pk_secret");
    await userEvent.click(copyButtons()[0]);
    await waitFor(() => expect(copyMock).toHaveBeenCalled());
    expect(copyMock).toHaveBeenCalledWith(
      "https://tron-jsonrpc.example.test/pk_secret",
    );
  });

  it("restores filters and the inner scroll position after returning from gateway details", async () => {
    const first = renderPanel();
    await screen.findByRole("link", { name: "Mainnet" });

    const search = screen.getByRole("textbox", { name: "searchAria" });
    await userEvent.type(search, "tron");
    const firstScroller = first.container.querySelector<HTMLElement>(
      '[data-slot="gateway-list-scroll"]',
    );
    expect(firstScroller).not.toBeNull();
    if (firstScroller) firstScroller.scrollTop = 240;

    await userEvent.click(screen.getByRole("link", { name: "Mainnet" }));
    first.unmount();

    const second = renderPanel();
    expect(
      await screen.findByRole("textbox", { name: "searchAria" }),
    ).toHaveValue("tron");
    const secondScroller = second.container.querySelector<HTMLElement>(
      '[data-slot="gateway-list-scroll"]',
    );
    expect(secondScroller).not.toBeNull();
    await waitFor(() => expect(secondScroller?.scrollTop).toBe(240));
    await waitFor(() =>
      expect(listGatewaysMock).toHaveBeenCalledWith(
        expect.objectContaining({ search: "tron" }),
      ),
    );
  });

  it("bulk-disables enabled gateways with one PATCH and updates status without another GET", async () => {
    const firstEnabled = makeGateway({
      id: "gw_on_1",
      network: "mainnet",
      version: 3,
    });
    const secondEnabled = makeGateway({
      id: "gw_on_2",
      network: "nile",
      version: 5,
    });
    const disabledGateway = makeGateway({
      id: "gw_off",
      chain: "ethereum",
      network: "sepolia",
      enabled: false,
      effective_enabled: false,
    });
    listGatewaysMock.mockImplementation(async () =>
      gatewayList([firstEnabled, secondEnabled, disabledGateway]),
    );
    bulkUpdateGatewaysMock.mockImplementationOnce(async (_appId, input) => {
      const items = [firstEnabled, secondEnabled].map((gateway) => ({
        ...gateway,
        enabled: input.enabled,
        effective_enabled: input.enabled,
        version: gateway.version + 1,
      }));
      return { total: items.length, items };
    });
    renderPanel();

    const disableAll = screen.getByRole("button", { name: "disableAll" });
    // The bulk buttons stay disabled until the gateway list resolves.
    await waitFor(() => expect(disableAll).toBeEnabled());
    await userEvent.click(disableAll);

    expect(bulkUpdateGatewaysMock).not.toHaveBeenCalled();
    const dialog = screen.getByRole("dialog");
    fireEvent.click(
      within(dialog).getByRole("button", {
        name: "disableDialog.confirm",
      }),
    );

    await waitFor(() =>
      expect(bulkUpdateGatewaysMock).toHaveBeenCalledTimes(1),
    );
    expect(bulkUpdateGatewaysMock).toHaveBeenCalledWith("app_1", {
      enabled: false,
      gateways: [
        { id: "gw_on_1", expected_version: 3 },
        { id: "gw_on_2", expected_version: 5 },
      ],
    });
    await waitFor(() =>
      expect(screen.getAllByText("status.disabled")).toHaveLength(3),
    );
    expect(listGatewaysMock).toHaveBeenCalledTimes(1);
  });

  it("refreshes the list once when an atomic bulk update fails", async () => {
    const disabledGateway = makeGateway({
      enabled: false,
      effective_enabled: false,
      version: 2,
    });
    listGatewaysMock.mockResolvedValue(gatewayList([disabledGateway]));
    bulkUpdateGatewaysMock.mockRejectedValueOnce(
      new ApiError({
        kind: "http",
        status: 400,
        message: "Gateway version conflict.",
      }),
    );
    renderPanel();

    const enableAll = screen.getByRole("button", { name: "enableAll" });
    await waitFor(() => expect(enableAll).toBeEnabled());
    await userEvent.click(enableAll);

    await waitFor(() => expect(listGatewaysMock).toHaveBeenCalledTimes(2));
    expect(bulkUpdateGatewaysMock).toHaveBeenCalledTimes(1);
    expect(toastErrorMock).toHaveBeenCalledWith("Gateway version conflict.");
    expect(screen.getByText("status.disabled")).toBeInTheDocument();
  });
});
