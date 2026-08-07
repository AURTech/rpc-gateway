import { describe, expect, it } from "vitest";

import type { RpcGatewayBase } from "@/api/gateways/client";
import type { RpcChain, RpcNetwork } from "@/lib/rpc-chain";

import { groupNetworks } from "./app-networks";

function gw(
  partial: Partial<RpcGatewayBase> & {
    id: string;
    chain: RpcChain;
    network: RpcNetwork;
  },
): RpcGatewayBase {
  return {
    name: partial.id,
    app_id: "app-1",
    app_name: "production",
    enabled: true,
    effective_enabled: true,
    version: 1,
    access_points: [
      {
        transport: "jsonrpc",
        url: `https://${partial.chain}.example/{path_key}`,
      },
    ],
    created_at: "2026-01-01T00:00:00.000Z",
    modified_at: "2026-01-01T00:00:00.000Z",
    ...partial,
  };
}

describe("groupNetworks", () => {
  it("groups by chain in registry order (ethereum before solana)", () => {
    // Pass solana first to prove ordering follows the registry, not input.
    const groups = groupNetworks([
      gw({ id: "sol-main", chain: "solana", network: "mainnet-beta" }),
      gw({ id: "eth-main", chain: "ethereum", network: "mainnet" }),
      gw({ id: "eth-sep", chain: "ethereum", network: "sepolia" }),
    ]);
    expect(groups.map((g) => g.chain)).toEqual(["ethereum", "solana"]);
    expect(groups[0].gateways).toHaveLength(2);
    expect(groups[1].gateways).toHaveLength(1);
  });

  it("orders mainnet before testnet within a chain", () => {
    // Input has the testnet first; grouping must reorder to mainnet-first.
    const groups = groupNetworks([
      gw({ id: "eth-sep", chain: "ethereum", network: "sepolia" }),
      gw({ id: "eth-main", chain: "ethereum", network: "mainnet" }),
    ]);
    expect(groups[0].gateways.map((g) => g.network)).toEqual([
      "mainnet",
      "sepolia",
    ]);
  });

  it("puts serving gateways ahead of paused ones, outranking the network order", () => {
    // The disabled mainnet would sort first on network rank alone.
    const groups = groupNetworks([
      gw({
        id: "eth-main",
        chain: "ethereum",
        network: "mainnet",
        enabled: false,
        effective_enabled: false,
      }),
      gw({ id: "eth-sep", chain: "ethereum", network: "sepolia" }),
    ]);
    expect(groups[0].gateways.map((g) => g.id)).toEqual([
      "eth-sep",
      "eth-main",
    ]);
  });

  it("keeps the network order within each enabled half", () => {
    const groups = groupNetworks([
      gw({
        id: "eth-sep-off",
        chain: "ethereum",
        network: "sepolia",
        enabled: false,
        effective_enabled: false,
      }),
      gw({ id: "eth-sep-on", chain: "ethereum", network: "sepolia" }),
      gw({
        id: "eth-main-off",
        chain: "ethereum",
        network: "mainnet",
        enabled: false,
        effective_enabled: false,
      }),
      gw({ id: "eth-main-on", chain: "ethereum", network: "mainnet" }),
    ]);
    expect(groups[0].gateways.map((g) => g.id)).toEqual([
      "eth-main-on",
      "eth-sep-on",
      "eth-main-off",
      "eth-sep-off",
    ]);
  });

  it("sorts on effective_enabled, so an app-blocked gateway ranks as paused", () => {
    // enabled=true but the owning App is off — the row reads "Disabled", so it
    // must not outrank a gateway that is actually serving.
    const groups = groupNetworks([
      gw({
        id: "eth-main-blocked",
        chain: "ethereum",
        network: "mainnet",
        enabled: true,
        effective_enabled: false,
      }),
      gw({ id: "eth-sep-live", chain: "ethereum", network: "sepolia" }),
    ]);
    expect(groups[0].gateways.map((g) => g.id)).toEqual([
      "eth-sep-live",
      "eth-main-blocked",
    ]);
  });
});
