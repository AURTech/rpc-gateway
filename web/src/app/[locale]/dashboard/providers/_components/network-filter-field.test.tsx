import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import type {
  RpcProviderNetworkPair,
  RpcProviderVendor,
} from "@/api/providers/client";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "@/components/ui/sheet";

import {
  NetworkFilterField,
  type NetworkFilterMode,
} from "./network-filter-field";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

function Harness({
  vendor = "alchemy",
  onNetworksChange = vi.fn(),
}: {
  vendor?: RpcProviderVendor;
  onNetworksChange?: (networks: RpcProviderNetworkPair[]) => void;
}) {
  const [mode, setMode] = useState<NetworkFilterMode>("none");
  const [networks, setNetworks] = useState<RpcProviderNetworkPair[]>([]);

  return (
    <NetworkFilterField
      vendor={vendor}
      mode={mode}
      onModeChange={setMode}
      networks={networks}
      onNetworksChange={(next) => {
        setNetworks(next);
        onNetworksChange(next);
      }}
      busy={false}
      idPrefix="provider-test"
    />
  );
}

describe("NetworkFilterField", () => {
  it("shows all three filter modes directly", () => {
    render(<Harness />);

    expect(
      screen.getByRole("radio", { name: "form.networkFilterNone" }),
    ).toBeChecked();
    expect(
      screen.getByRole("radio", { name: "form.networkFilterOnly" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("radio", { name: "form.networkFilterIgnore" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: "form.networkFilter" }),
    ).not.toBeInTheDocument();
  });

  it("searches and selects multiple chain and network pairs without an Add step", async () => {
    const user = userEvent.setup();
    const onNetworksChange = vi.fn();
    render(<Harness onNetworksChange={onNetworksChange} />);

    await user.click(
      screen.getByRole("radio", { name: "form.networkFilterOnly" }),
    );

    const input = screen.getByPlaceholderText("form.chainNetworkSearch");
    await user.type(input, "ethereum");
    await user.click(
      await screen.findByRole("option", { name: "EthereumSepolia" }),
    );

    expect(onNetworksChange).toHaveBeenLastCalledWith([
      { chain: "ethereum", network: "sepolia" },
    ]);

    await user.clear(input);
    await user.type(input, "Polygon");
    const listbox = await screen.findByRole("listbox");
    await user.click(
      within(listbox).getByRole("option", { name: "PolygonMainnet" }),
    );

    expect(onNetworksChange).toHaveBeenLastCalledWith([
      { chain: "ethereum", network: "sepolia" },
      { chain: "polygon", network: "mainnet" },
    ]);
    expect(
      screen.queryByRole("button", { name: "form.addNetwork" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Ethereum · Sepolia")).toBeInTheDocument();
    expect(screen.getByText("Polygon · Mainnet")).toBeInTheDocument();
  });

  it("keeps the options popup inside a Sheet so wheel scrolling is allowed", async () => {
    const user = userEvent.setup();
    render(
      <Sheet open onOpenChange={() => {}}>
        <SheetContent>
          <SheetTitle>Provider</SheetTitle>
          <SheetDescription>Edit provider</SheetDescription>
          <Harness />
        </SheetContent>
      </Sheet>,
    );

    await user.click(
      screen.getByRole("radio", { name: "form.networkFilterOnly" }),
    );
    await user.click(screen.getByPlaceholderText("form.chainNetworkSearch"));

    const listbox = await screen.findByRole("listbox");
    expect(listbox.closest('[data-slot="sheet-content"]')).not.toBeNull();
  });

  it("offers the selected vendor's supported non-EVM networks", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<Harness vendor="drpc" />);
    await user.click(
      screen.getByRole("radio", { name: "form.networkFilterOnly" }),
    );
    const input = screen.getByPlaceholderText("form.chainNetworkSearch");
    await user.type(input, "Litecoin");
    expect(screen.queryByRole("option")).not.toBeInTheDocument();

    rerender(<Harness vendor="alchemy" />);
    const alchemyInput = screen.getByPlaceholderText("form.chainNetworkSearch");
    await user.clear(alchemyInput);
    await user.type(alchemyInput, "Litecoin");
    expect(
      await screen.findByRole("option", { name: "LitecoinMainnet" }),
    ).toBeInTheDocument();
  });
});
