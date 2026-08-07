export const CHAINS = [
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

export const NETWORKS = [
  "mainnet",
  "mainnet-beta",
  "sepolia",
  "amoy",
  "testnet",
  "devnet",
  "nile",
] as const;

export type Chain = (typeof CHAINS)[number];
export type Network = (typeof NETWORKS)[number];

type ChainDefinition = {
  label: string;
  networks: readonly Network[];
};

export const CHAIN_CATALOG = {
  ethereum: { label: "Ethereum", networks: ["mainnet", "sepolia"] },
  polygon: { label: "Polygon", networks: ["mainnet", "amoy"] },
  bsc: { label: "BNB Smart Chain", networks: ["mainnet", "testnet"] },
  arbitrum: { label: "Arbitrum", networks: ["mainnet", "sepolia"] },
  optimism: { label: "Optimism", networks: ["mainnet", "sepolia"] },
  base: { label: "Base", networks: ["mainnet", "sepolia"] },
  solana: { label: "Solana", networks: ["mainnet-beta", "devnet"] },
  bitcoin: { label: "Bitcoin", networks: ["mainnet", "testnet"] },
  litecoin: { label: "Litecoin", networks: ["mainnet", "testnet"] },
  tron: { label: "TRON", networks: ["mainnet", "nile"] },
} as const satisfies Record<Chain, ChainDefinition>;
