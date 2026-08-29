export type RpcMethodProtocol = "evm" | "tron" | "svm" | "utxo";

export const RPC_CHAINS = [
  "ethereum",
  "polygon",
  "bsc",
  "arbitrum",
  "optimism",
  "base",
  "solana",
  "bitcoin",
  "litecoin",
  "tron",
] as const;

export const RPC_NETWORKS = [
  "mainnet",
  "mainnet-beta",
  "sepolia",
  "amoy",
  "testnet",
  "devnet",
  "nile",
] as const;

export type RpcChain = (typeof RPC_CHAINS)[number];
export type RpcNetwork = (typeof RPC_NETWORKS)[number];

const RPC_CHAIN_SET: ReadonlySet<string> = new Set(RPC_CHAINS);

/** Narrow an arbitrary string to a known {@link RpcChain}. Use to filter
 *  server-sent chain slugs so an unknown value can't break rendering. */
export function isRpcChain(value: string): value is RpcChain {
  return RPC_CHAIN_SET.has(value);
}

type NetworkSpec = {
  label: string;
  chainId: number | null;
};

type ChainSpec = {
  label: string;
  short: string;
  /** URL slug used by the public JSON-RPC entry point. */
  slug: string;
  /** Chain color as a reference to its `--chain-*` token in globals.css.
   *  A `var()` ref rather than a literal so the token file stays the single
   *  source of truth; anything needing a tint composes with `color-mix()`. */
  accent: string;
  /** Lighter variant used when a series or badge stands for a testnet, so a
   *  chain's mainnet and testnet stay distinguishable at the same hue. */
  accentTestnet: string;
  networks: Partial<Record<RpcNetwork, NetworkSpec>>;
};

export const RPC_CHAIN_REGISTRY: Record<RpcChain, ChainSpec> = {
  ethereum: {
    label: "Ethereum",
    short: "ETH",
    slug: "eth",
    accent: "var(--chain-ethereum)",
    accentTestnet: "var(--chain-ethereum-testnet)",
    networks: {
      mainnet: { label: "Mainnet", chainId: 1 },
      sepolia: { label: "Sepolia", chainId: 11155111 },
    },
  },
  polygon: {
    label: "Polygon",
    short: "POL",
    slug: "pol",
    accent: "var(--chain-polygon)",
    accentTestnet: "var(--chain-polygon-testnet)",
    networks: {
      mainnet: { label: "Mainnet", chainId: 137 },
      amoy: { label: "Amoy", chainId: 80002 },
    },
  },
  bsc: {
    label: "BNB Smart Chain",
    short: "BNB",
    slug: "bnb",
    accent: "var(--chain-bsc)",
    accentTestnet: "var(--chain-bsc-testnet)",
    networks: {
      mainnet: { label: "Mainnet", chainId: 56 },
      testnet: { label: "Testnet", chainId: 97 },
    },
  },
  arbitrum: {
    label: "Arbitrum",
    short: "ARB",
    slug: "arb",
    accent: "var(--chain-arbitrum)",
    accentTestnet: "var(--chain-arbitrum-testnet)",
    networks: {
      mainnet: { label: "Mainnet", chainId: 42161 },
      sepolia: { label: "Sepolia", chainId: 421614 },
    },
  },
  optimism: {
    label: "Optimism",
    short: "OP",
    slug: "op",
    accent: "var(--chain-optimism)",
    accentTestnet: "var(--chain-optimism-testnet)",
    networks: {
      mainnet: { label: "Mainnet", chainId: 10 },
      sepolia: { label: "Sepolia", chainId: 11155420 },
    },
  },
  base: {
    label: "Base",
    short: "BASE",
    slug: "base",
    accent: "var(--chain-base)",
    accentTestnet: "var(--chain-base-testnet)",
    networks: {
      mainnet: { label: "Mainnet", chainId: 8453 },
      sepolia: { label: "Sepolia", chainId: 84532 },
    },
  },
  solana: {
    label: "Solana",
    short: "SOL",
    slug: "sol",
    accent: "var(--chain-solana)",
    accentTestnet: "var(--chain-solana-testnet)",
    networks: {
      // The wire identifier stays `mainnet-beta` — it is the API enum value and
      // the gateway URL segment — but the console always shows it as "Mainnet".
      "mainnet-beta": { label: "Mainnet", chainId: null },
      devnet: { label: "Devnet", chainId: null },
    },
  },
  bitcoin: {
    label: "Bitcoin",
    short: "BTC",
    slug: "btc",
    accent: "var(--chain-bitcoin)",
    accentTestnet: "var(--chain-bitcoin-testnet)",
    networks: {
      mainnet: { label: "Mainnet", chainId: null },
      testnet: { label: "Testnet", chainId: null },
    },
  },
  litecoin: {
    label: "Litecoin",
    short: "LTC",
    slug: "ltc",
    accent: "var(--chain-litecoin)",
    accentTestnet: "var(--chain-litecoin-testnet)",
    networks: {
      mainnet: { label: "Mainnet", chainId: null },
      testnet: { label: "Testnet", chainId: null },
    },
  },
  tron: {
    label: "TRON",
    short: "TRX",
    slug: "tron",
    accent: "var(--chain-tron)",
    accentTestnet: "var(--chain-tron-testnet)",
    networks: {
      mainnet: { label: "Mainnet", chainId: 728126428 },
      nile: { label: "Nile", chainId: 3448148188 },
    },
  },
};

/**
 * JSON-RPC protocol family a chain speaks. EVM chains share one method family;
 * Solana and TRON have their own.
 */
const CHAIN_PROTOCOL: Record<RpcChain, RpcMethodProtocol> = {
  ethereum: "evm",
  polygon: "evm",
  bsc: "evm",
  arbitrum: "evm",
  optimism: "evm",
  base: "evm",
  solana: "svm",
  bitcoin: "utxo",
  litecoin: "utxo",
  tron: "tron",
};

export function chainProtocol(chain: RpcChain): RpcMethodProtocol {
  return CHAIN_PROTOCOL[chain];
}

export function chainSlug(chain: RpcChain): string {
  return RPC_CHAIN_REGISTRY[chain].slug;
}

export function chainLabel(chain: RpcChain): string {
  return RPC_CHAIN_REGISTRY[chain].label;
}

/**
 * The chain's color, as a `var(--chain-*)` reference.
 *
 * Pass `network` wherever the color stands for a single (chain, network) pair
 * — a by-network chart plots a chain's mainnet and testnet as two separate
 * series, and without the lighter testnet variant they would draw in exactly
 * the same color. Omit it in chain-only contexts — same convention as
 * `ChainIcon`.
 */
export function chainAccent(chain: RpcChain, network?: RpcNetwork): string {
  const spec = RPC_CHAIN_REGISTRY[chain];
  return network !== undefined && isTestnetNetwork(network)
    ? spec.accentTestnet
    : spec.accent;
}

export function networksFor(chain: RpcChain): RpcNetwork[] {
  return Object.keys(RPC_CHAIN_REGISTRY[chain].networks) as RpcNetwork[];
}

export function networkLabel(chain: RpcChain, network: RpcNetwork): string {
  return RPC_CHAIN_REGISTRY[chain].networks[network]?.label ?? network;
}

export function chainId(chain: RpcChain, network: RpcNetwork): number | null {
  return RPC_CHAIN_REGISTRY[chain].networks[network]?.chainId ?? null;
}

/** Networks carrying real value. Everything else in {@link RPC_NETWORKS} is a
 *  testnet — a deny-list by mainnet on purpose, so a network added later is
 *  flagged as a testnet by default instead of silently passing as production. */
const MAINNET_NETWORKS: ReadonlySet<string> = new Set([
  "mainnet",
  "mainnet-beta",
]);

/** Whether a network is a testnet. The API carries no such flag — chain and
 *  network are the only fields — so the distinction lives here. */
export function isTestnetNetwork(network: RpcNetwork): boolean {
  return !MAINNET_NETWORKS.has(network);
}
