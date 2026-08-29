import type {
  RpcProviderNetworkPair,
  RpcProviderVendor,
} from "@/api/providers/client";
import { networksFor, RPC_CHAINS } from "@/lib/rpc-chain";

const EVM_NETWORKS = [
  "ethereum:mainnet",
  "ethereum:sepolia",
  "polygon:mainnet",
  "polygon:amoy",
  "bsc:mainnet",
  "bsc:testnet",
  "arbitrum:mainnet",
  "arbitrum:sepolia",
  "optimism:mainnet",
  "optimism:sepolia",
  "base:mainnet",
  "base:sepolia",
] as const;

const NON_EVM_NETWORKS = [
  "solana:mainnet-beta",
  "solana:devnet",
  "bitcoin:mainnet",
  "bitcoin:testnet",
  "litecoin:mainnet",
  "litecoin:testnet",
] as const;

const ALL_NETWORKS = [
  ...EVM_NETWORKS,
  ...NON_EVM_NETWORKS,
  "tron:mainnet",
  "tron:nile",
] as const;

const TENDERLY_NETWORKS = EVM_NETWORKS.filter(
  (network) => !network.startsWith("bsc:"),
);

export const PROVIDER_NETWORKS: Record<
  RpcProviderVendor,
  ReadonlySet<string>
> = {
  alchemy: new Set(ALL_NETWORKS),
  quicknode: new Set(ALL_NETWORKS),
  chainstack: new Set([
    ...EVM_NETWORKS,
    "solana:mainnet-beta",
    "solana:devnet",
    "bitcoin:mainnet",
    "bitcoin:testnet",
    "litecoin:mainnet",
    "tron:mainnet",
    "tron:nile",
  ]),
  drpc: new Set([
    ...EVM_NETWORKS,
    "solana:mainnet-beta",
    "solana:devnet",
    "bitcoin:mainnet",
    "tron:mainnet",
  ]),
  tenderly: new Set(TENDERLY_NETWORKS),
};

export function providerSupportsNetwork(
  vendor: RpcProviderVendor,
  pair: RpcProviderNetworkPair,
): boolean {
  return PROVIDER_NETWORKS[vendor].has(`${pair.chain}:${pair.network}`);
}

const ALL_PROVIDER_NETWORKS: RpcProviderNetworkPair[] = RPC_CHAINS.flatMap(
  (chain) => networksFor(chain).map((network) => ({ chain, network })),
);

/** Every chain/network pair a vendor can discover, in catalog order. */
export function providerNetworksForVendor(
  vendor: RpcProviderVendor,
): RpcProviderNetworkPair[] {
  return ALL_PROVIDER_NETWORKS.filter((pair) =>
    providerSupportsNetwork(vendor, pair),
  );
}
