import {
  networksFor,
  RPC_CHAINS,
  type RpcChain,
  type RpcNetwork,
} from "@/lib/rpc-chain";

export type ChainCatalogGroup = {
  chain: RpcChain;
  networks: readonly RpcNetwork[];
};

/**
 * Stable identity for a picked network in the create-app wizard. The app — and
 * therefore its gateways — doesn't exist while the user is choosing, so the
 * selection is keyed by (chain, network) instead of by gateway id, and mapped
 * onto the real gateways only once the app has been created.
 */
export function networkKey(chain: RpcChain, network: RpcNetwork): string {
  return `${chain}:${network}`;
}

/**
 * The chains and networks offered by the wizard, read straight from the client
 * registry: `RPC_CHAINS` order is the render order, and each chain's registry
 * lists its mainnet before its testnet. This mirrors the server catalog the
 * backend provisions gateways from, so what the user picks here lines up with
 * the gateways that exist after create.
 */
export const CHAIN_CATALOG: readonly ChainCatalogGroup[] = RPC_CHAINS.map(
  (chain) => ({ chain, networks: networksFor(chain) }),
);

/** Every network key in the catalog — the "select all" set. */
export const ALL_NETWORK_KEYS: readonly string[] = CHAIN_CATALOG.flatMap(
  (group) => group.networks.map((network) => networkKey(group.chain, network)),
);
