import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type {
  RpcGatewayBase,
  RpcGatewayTransport,
} from "@/api/gateways/client";

import { makeGateway as sharedGateway } from "@/test/fixtures";

import { GatewayNetworkRow } from "./gateway-network-row";

// next-intl is stubbed to echo the key, so the copy button's accessible name is
// `table.copyEndpoint` and the "not available" placeholder renders as
// `transport.<name>` / `noEndpoint` — assertions target those.
vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

vi.mock("@/i18n/navigation", async () =>
  (await import("@/test/navigation")).navigationMock(),
);

/** A TRON gateway exposing all three transports, one per row the test surfaces. */
function makeGateway(overrides: Partial<RpcGatewayBase> = {}): RpcGatewayBase {
  return sharedGateway({
    id: "gw_tron",
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
      { transport: "grpc", url: "grpcs://tron-grpc.example.test:443" },
    ],
    ...overrides,
  });
}

function renderRow(
  overrides: Partial<RpcGatewayBase> = {},
  options: {
    transport?: RpcGatewayTransport;
    pathKey?: string | null;
    pathKeyCopyDisabled?: boolean;
  } = {},
) {
  const onCopy = vi.fn();
  render(
    <ul>
      <GatewayNetworkRow
        gateway={makeGateway(overrides)}
        appId="app_1"
        transport={options.transport ?? "jsonrpc"}
        onCopy={onCopy}
        pathKey={options.pathKey}
        pathKeyCopyDisabled={options.pathKeyCopyDisabled}
      />
    </ul>,
  );
  return { onCopy };
}

const copyButton = () =>
  screen.getByRole("button", { name: "table.copyEndpoint" });

describe("GatewayNetworkRow", () => {
  it("shows Solana mainnet-beta as Mainnet in the gateway list", () => {
    renderRow({
      chain: "solana",
      network: "mainnet-beta",
      name: "solana-mainnet-beta",
    });

    expect(screen.getByRole("link", { name: "Mainnet" })).toBeInTheDocument();
    expect(screen.queryByText("Mainnet Beta")).not.toBeInTheDocument();
  });

  it("shows the selected protocol's access point", () => {
    renderRow();

    expect(
      screen.getByText("https://tron-jsonrpc.example.test/{path_key}"),
    ).toBeInTheDocument();
    // Only the selected protocol is rendered; the others stay hidden.
    expect(
      screen.queryByText("https://tron-httpapi.example.test/{path_key}"),
    ).not.toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "table.copyEndpoint" }),
    ).toHaveLength(1);
  });

  it("switches the surfaced URL with the transport prop", () => {
    renderRow({}, { transport: "http_api" });

    expect(
      screen.getByText("https://tron-httpapi.example.test/{path_key}"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("https://tron-jsonrpc.example.test/{path_key}"),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Mainnet" })).toHaveAttribute(
      "href",
      "/dashboard/apps/app_1/gateways/gw_tron?transport=http_api",
    );
  });

  it("renders a placeholder when the selected protocol is unavailable", () => {
    renderRow(
      {
        chain: "ethereum",
        network: "mainnet",
        access_points: [
          {
            transport: "jsonrpc",
            url: "https://eth-jsonrpc.example.test/{path_key}",
          },
        ],
      },
      { transport: "http_api" },
    );

    expect(screen.getByText("noEndpoint")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "table.copyEndpoint" }),
    ).not.toBeInTheDocument();
  });

  it("copies the selected access point's URL", async () => {
    const { onCopy } = renderRow({}, { transport: "http_api" });

    await userEvent.click(copyButton());
    expect(onCopy).toHaveBeenCalledWith(
      "https://tron-httpapi.example.test/{path_key}",
    );
  });

  it("fills path-authenticated endpoints with the visible key", async () => {
    const { onCopy } = renderRow({}, { pathKey: "pk_complete_value" });

    expect(
      screen.getByText("https://tron-jsonrpc.example.test/pk_complete_value"),
    ).toBeInTheDocument();

    await userEvent.click(copyButton());
    expect(onCopy).toHaveBeenCalledWith(
      "https://tron-jsonrpc.example.test/pk_complete_value",
    );
  });

  it("disables path-key copies until the key is available", () => {
    renderRow({}, { pathKeyCopyDisabled: true });
    expect(copyButton()).toBeDisabled();
  });

  it("disables copy actions for a disabled gateway", () => {
    renderRow({ effective_enabled: false });
    expect(copyButton()).toBeDisabled();
  });
});
