import { describe, expect, it } from "vitest";

import { NETWORKS } from "./blockchain";
import {
  chainAccent,
  chainId,
  chainLabel,
  chainProtocol,
  chainSlug,
  isTestnetNetwork,
  networkLabel,
  networksFor,
  RPC_CHAINS,
  RPC_NETWORKS,
} from "./rpc-chain";

describe("rpc chain registry", () => {
  it("includes TRON mainnet and Nile metadata", () => {
    expect(RPC_CHAINS).toContain("tron");
    expect(RPC_NETWORKS).toContain("nile");
    expect(chainLabel("tron")).toBe("TRON");
    expect(chainSlug("tron")).toBe("tron");
    expect(chainAccent("tron")).toBe("#EF0027");
    expect(networksFor("tron")).toEqual(["mainnet", "nile"]);
    expect(networkLabel("tron", "nile")).toBe("Nile");
    expect(chainId("tron", "mainnet")).toBe(728126428);
    expect(chainId("tron", "nile")).toBe(3448148188);
  });

  it("includes UTXO chain metadata returned by the backend", () => {
    expect(RPC_CHAINS).toContain("bitcoin");
    expect(RPC_CHAINS).toContain("litecoin");
    expect(chainLabel("bitcoin")).toBe("Bitcoin");
    expect(chainLabel("litecoin")).toBe("Litecoin");
    expect(chainSlug("bitcoin")).toBe("btc");
    expect(chainSlug("litecoin")).toBe("ltc");
    expect(chainAccent("bitcoin")).toBe("#F7931A");
    expect(chainAccent("litecoin")).toBe("#345D9D");
    expect(networksFor("bitcoin")).toEqual(["mainnet", "testnet"]);
    expect(networksFor("litecoin")).toEqual(["mainnet", "testnet"]);
    expect(networkLabel("bitcoin", "testnet")).toBe("Testnet");
    expect(networkLabel("litecoin", "testnet")).toBe("Testnet");
    expect(chainId("bitcoin", "mainnet")).toBeNull();
    expect(chainId("litecoin", "testnet")).toBeNull();
    expect(chainProtocol("bitcoin")).toBe("utxo");
    expect(chainProtocol("litecoin")).toBe("utxo");
  });

  it("labels Solana's production network Mainnet, not Mainnet Beta", () => {
    // The identifier keeps the wire value the API and gateway URLs use; only
    // the display label drops the "Beta".
    expect(networksFor("solana")).toEqual(["mainnet-beta", "devnet"]);
    expect(networkLabel("solana", "mainnet-beta")).toBe("Mainnet");
  });

  it("treats every network except the two mainnets as a testnet", () => {
    expect(isTestnetNetwork("mainnet")).toBe(false);
    expect(isTestnetNetwork("mainnet-beta")).toBe(false);
    expect(isTestnetNetwork("sepolia")).toBe(true);
    expect(isTestnetNetwork("amoy")).toBe(true);
    expect(isTestnetNetwork("testnet")).toBe(true);
    expect(isTestnetNetwork("devnet")).toBe(true);
    expect(isTestnetNetwork("nile")).toBe(true);
  });

  it("covers every registry network so a new one can't slip through", () => {
    // Guards the deny-list: adding a network to RPC_NETWORKS without deciding
    // its side here would leave it silently classified as a testnet.
    expect(
      RPC_NETWORKS.filter((network) => !isTestnetNetwork(network)),
    ).toEqual(["mainnet", "mainnet-beta"]);
  });

  it("keeps the blockchain.ts network list in step with the registry", () => {
    // `Network` and `RpcNetwork` are separate declarations of the same union,
    // which is what lets blockchain.ts consumers (the endpoints client, the
    // edit-endpoint sheet) hand their `network` straight to isTestnetNetwork.
    // Let them drift and that call stops compiling — fail here first, with a
    // message that says which list moved.
    expect([...NETWORKS]).toEqual([...RPC_NETWORKS]);
  });
});
