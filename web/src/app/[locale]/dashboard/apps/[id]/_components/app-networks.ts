import type { RpcGatewayBase } from "@/api/gateways/client";
import {
  networksFor,
  RPC_CHAINS,
  type RpcChain,
  type RpcNetwork,
} from "@/lib/rpc-chain";

export type ChainGroup = { chain: RpcChain; gateways: RpcGatewayBase[] };

// Registry order index so groups render in the same order as `RPC_CHAINS`.
const CHAIN_ORDER: ReadonlyMap<RpcChain, number> = new Map(
  RPC_CHAINS.map((chain, index) => [chain, index] as const),
);

/**
 * Bucket the (already server-filtered, server-sorted) gateways into per-chain
 * groups ordered by the chain registry. Within a group, the gateways actually
 * serving traffic come first — the rows a user acts on, and the ones whose URL
 * is live and copyable — and networks are ordered by the chain registry within
 * each of those halves (mainnet first, then the testnet: `mainnet-beta`, named
 * testnets like `sepolia`/`nile`). `Array` sort is stable, so any remaining ties
 * keep the server's `created_at` order. Empty groups never appear because a
 * chain only gets a bucket once it has a gateway.
 *
 * The enabled key is `effective_enabled`, matching the state each row displays:
 * a gateway enabled under a disabled App serves nothing and reads as "Disabled",
 * so it must not sort above a live one. When the App itself is disabled every
 * gateway ties there and the order falls back to the network ranking.
 */
export function groupNetworks(gateways: RpcGatewayBase[]): ChainGroup[] {
  const byChain = new Map<RpcChain, RpcGatewayBase[]>();
  for (const gw of gateways) {
    const bucket = byChain.get(gw.chain);
    if (bucket) bucket.push(gw);
    else byChain.set(gw.chain, [gw]);
  }

  const groups: ChainGroup[] = [];
  for (const [chain, list] of byChain) {
    const networkOrder = networksFor(chain);
    list.sort(
      (a, b) =>
        enabledRank(a) - enabledRank(b) ||
        networkRank(networkOrder, a.network) -
          networkRank(networkOrder, b.network),
    );
    groups.push({ chain, gateways: list });
  }
  groups.sort(
    (a, b) => (CHAIN_ORDER.get(a.chain) ?? 0) - (CHAIN_ORDER.get(b.chain) ?? 0),
  );
  return groups;
}

/** Serving gateways sort first (0) and paused ones last (1). */
function enabledRank(gateway: RpcGatewayBase): number {
  return gateway.effective_enabled ? 0 : 1;
}

/** Registry index of a network within its chain (mainnet first); unknowns last. */
function networkRank(
  order: readonly RpcNetwork[],
  network: RpcNetwork,
): number {
  const index = order.indexOf(network);
  return index === -1 ? order.length : index;
}
