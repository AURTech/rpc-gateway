import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RpcAppDetail } from "@/api/apps/client";
import { listGateways, type RpcGatewayBase } from "@/api/gateways/client";
import { useAppQuery } from "@/hooks/use-apps";
import { gatewayList, makeGateway as sharedGateway } from "@/test/fixtures";
import { createTestQueryClient, renderWithQuery } from "@/test/query";

import { AppOverviewContent } from "./app-overview-content";
import type { AppOverviewTab } from "./use-app-overview-tab";
import { useGatewayPathKey } from "./use-gateway-path-key";

const { replaceMock } = vi.hoisted(() => ({ replaceMock: vi.fn() }));

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

vi.mock("@/i18n/navigation", async () =>
  (await import("@/test/navigation")).navigationMock({
    pathname: "/dashboard/apps/app_1",
    replace: replaceMock,
  }),
);

vi.mock("@/hooks/use-apps", () => ({
  useAppQuery: vi.fn(),
}));

vi.mock("./use-gateway-path-key", () => ({
  useGatewayPathKey: vi.fn(),
}));

// The Gateways tab owns a large management table. Its integration is covered
// separately; these tests only need to prove the tab contract and app scope.
vi.mock("./app-networks-panel", () => ({
  AppNetworksPanel: ({ appId }: { appId: string }) => (
    <div data-testid="gateways-panel">{appId}</div>
  ),
}));

vi.mock("./gateway-api-key-copy", () => ({
  GatewayApiKeyCopy: () => <div data-testid="gateway-key" />,
}));

vi.mock("@/api/gateways/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/gateways/client")>();
  return { ...actual, listGateways: vi.fn() };
});

const useAppQueryMock = vi.mocked(useAppQuery);
const useGatewayPathKeyMock = vi.mocked(useGatewayPathKey);
const listGatewaysMock = vi.mocked(listGateways);

const VISITED_KEY = "rpc-gateway:app-overview-visited";

function makeApp(overrides: Partial<RpcAppDetail> = {}): RpcAppDetail {
  return {
    id: "app_1",
    name: "production",
    enabled: true,
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    modified_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

/** The backend hands this app's gateways `{api_key}` templates (see host.py). */
function makeGateway(overrides: Partial<RpcGatewayBase> = {}): RpcGatewayBase {
  return sharedGateway({
    access_points: [
      {
        transport: "jsonrpc",
        url: "https://eth-jsonrpc.example.test/{api_key}",
      },
    ],
    ...overrides,
  });
}

function mockAppLoaded(app = makeApp()) {
  useAppQueryMock.mockReturnValue({
    data: app,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useAppQuery>);
}

function renderContent(initialTab?: AppOverviewTab) {
  const client = createTestQueryClient();
  return renderWithQuery(
    <AppOverviewContent appId="app_1" initialTab={initialTab} />,
    client,
  );
}

afterEach(() => {
  vi.clearAllMocks();
  // The visit history decides the default tab, so each test starts fresh.
  window.localStorage.clear();
});

useGatewayPathKeyMock.mockReturnValue({
  pathKey: "ak_active_visible",
  status: "available",
  refetchKeys: vi.fn(),
  isRefetchingKeys: false,
});

describe("AppOverviewContent", () => {
  it("renders a first request with the active API key in the endpoint", async () => {
    mockAppLoaded();
    listGatewaysMock.mockResolvedValue(gatewayList([makeGateway({})]));

    renderContent();

    const pageHeader = screen.getByRole("banner");
    expect(within(pageHeader).getByTestId("gateway-key")).toBeInTheDocument();
    // Sample method for the chain's protocol (evm -> eth_blockNumber).
    expect(await screen.findByText("eth_blockNumber")).toBeInTheDocument();
    // Both the Endpoint row and cURL example are immediately usable.
    await waitFor(() => {
      expect(
        screen.getAllByText(/eth-jsonrpc\.example\.test\/ak_active_visible/)
          .length,
      ).toBe(2);
    });
    expect(screen.queryByText(/\{api_key\}/)).not.toBeInTheDocument();
  });

  it("shows a get-started pointer and no quickstart when the app has no gateway", async () => {
    mockAppLoaded();
    listGatewaysMock.mockResolvedValue(gatewayList([]));

    renderContent();

    const cta = await screen.findByRole("link", { name: "cta" });
    expect(cta).toHaveAttribute("href", "/dashboard/apps/app_1/gateways");
    expect(screen.queryByText("eth_blockNumber")).not.toBeInTheDocument();
  });

  it("offers only networks that are effectively enabled for this app", async () => {
    mockAppLoaded();
    listGatewaysMock.mockResolvedValue(
      gatewayList([
        makeGateway({}),
        makeGateway({
          id: "gw_polygon",
          name: "polygon-mainnet",
          chain: "polygon",
          effective_enabled: false,
          access_points: [
            {
              transport: "jsonrpc",
              url: "https://polygon-jsonrpc.example.test/{api_key}",
            },
          ],
        }),
      ]),
    );

    renderContent();

    await userEvent.click(
      await screen.findByRole("combobox", { name: "selectorLabel" }),
    );

    expect(
      await screen.findByRole("option", { name: "Ethereum Mainnet" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("option", { name: "Polygon Mainnet" }),
    ).not.toBeInTheDocument();
    expect(listGatewaysMock).toHaveBeenCalledWith({
      app_id: "app_1",
      enabled: true,
      size: 50,
    });
  });

  it("shows the setup pointer when this app has no effectively enabled network", async () => {
    mockAppLoaded();
    listGatewaysMock.mockResolvedValue(
      gatewayList([makeGateway({ effective_enabled: false })]),
    );

    renderContent();

    expect(await screen.findByRole("link", { name: "cta" })).toHaveAttribute(
      "href",
      "/dashboard/apps/app_1/gateways",
    );
    expect(screen.queryByText("eth_blockNumber")).not.toBeInTheDocument();
  });

  it("offers only the protocols the gateway actually exposes", async () => {
    mockAppLoaded();
    listGatewaysMock.mockResolvedValue(
      gatewayList([
        makeGateway({
          access_points: [
            {
              transport: "jsonrpc",
              url: "https://eth-jsonrpc.example.test/{api_key}",
            },
          ],
        }),
      ]),
    );

    renderContent();
    await userEvent.click(
      await screen.findByRole("combobox", { name: "protocolLabel" }),
    );

    const options = await screen.findAllByRole("option");
    // http_api has no access point on this gateway, so it isn't offered.
    expect(options.map((o) => o.textContent)).toEqual(["transport.jsonrpc"]);
  });

  it("swaps in gateway management and mirrors the tab into the URL", async () => {
    mockAppLoaded();
    listGatewaysMock.mockResolvedValue(gatewayList([makeGateway({})]));

    renderContent();
    await screen.findByText("eth_blockNumber");

    await userEvent.click(screen.getByRole("tab", { name: "tabs.gateways" }));

    expect(await screen.findByTestId("gateways-panel")).toHaveTextContent(
      "app_1",
    );
    expect(screen.queryByText("eth_blockNumber")).not.toBeInTheDocument();
    expect(replaceMock).toHaveBeenCalledWith(
      "/dashboard/apps/app_1?tab=gateways",
    );
  });

  it("opens on setup for a first visit, then on gateways once the app is known", async () => {
    mockAppLoaded();
    listGatewaysMock.mockResolvedValue(gatewayList([makeGateway({})]));

    const first = renderContent();
    // Nothing stored yet, so the first visit walks the user through setup...
    expect(await screen.findByText("eth_blockNumber")).toBeInTheDocument();
    first.unmount();

    // ...and opening it is what records the visit.
    expect(window.localStorage.getItem(VISITED_KEY)).toContain("app_1");

    renderContent();
    expect(await screen.findByTestId("gateways-panel")).toBeInTheDocument();
  });

  it("keeps a different app on setup", async () => {
    mockAppLoaded();
    listGatewaysMock.mockResolvedValue(gatewayList([makeGateway({})]));
    window.localStorage.setItem(VISITED_KEY, JSON.stringify(["app_other"]));

    renderContent();

    expect(await screen.findByText("eth_blockNumber")).toBeInTheDocument();
    expect(screen.queryByTestId("gateways-panel")).not.toBeInTheDocument();
  });

  it("lets an explicit ?tab= override the remembered default", async () => {
    mockAppLoaded();
    listGatewaysMock.mockResolvedValue(gatewayList([makeGateway({})]));
    // Visited before, so the default would be gateways — the URL says otherwise.
    window.localStorage.setItem(VISITED_KEY, JSON.stringify(["app_1"]));

    renderContent("setup");

    expect(await screen.findByText("eth_blockNumber")).toBeInTheDocument();
    expect(screen.queryByTestId("gateways-panel")).not.toBeInTheDocument();
  });
});
