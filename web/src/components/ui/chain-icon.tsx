import {
  chainLabel,
  chainSlug,
  isTestnetNetwork,
  type RpcChain,
  type RpcNetwork,
} from "@/lib/rpc-chain";
import { cn } from "@/lib/utils";

const CHAIN_ICON_BASE = "https://cdn.aurpay.net/cryptocurrency-symbol";

export function chainIconUrl(chain: RpcChain): string {
  return `${CHAIN_ICON_BASE}/${chainSlug(chain)}.svg`;
}

/**
 * Chain logo rendered from the public CDN at
 * cdn.aurpay.net/cryptocurrency-symbol/<chain-slug>.svg.
 *
 * The CDN has one artwork per chain, so a mainnet and its testnet would
 * otherwise be pixel-identical. Pass `network` wherever the icon stands for a
 * single (chain, network) pair: a testnet is then wrapped in a dark dashed
 * outline (see `chain-testnet-mark` in globals.css). Omit it in chain-only
 * contexts (filters, `ChainGroup`) where the icon means "the chain" and a
 * testnet marker would be wrong.
 *
 * Plain <img> on purpose — these are tiny, decorative SVGs and routing them
 * through next/image would force us to register the CDN as a remotePatterns
 * host for zero size or perf win. Browsers also cache SVGs across the table
 * trivially since every row shares the same URL.
 */
export function ChainIcon({
  chain,
  network,
  className,
}: {
  chain: RpcChain;
  network?: RpcNetwork;
  className?: string;
}) {
  const testnet = network !== undefined && isTestnetNetwork(network);

  const image = (
    // biome-ignore lint/performance/noImgElement: tiny static SVG from a CDN; routing through next/image would only add a remotePatterns config and an image-optimizer hop for zero benefit.
    <img
      src={chainIconUrl(chain)}
      // Chain only, never the network. In the chain·network dropdowns the
      // option's visible text is just the network name, so this alt is what
      // supplies the chain half of the accessible name — appending the network
      // here would say it twice. Screen readers get the testnet signal from
      // that visible network name, which is why the mark below is decorative.
      alt={chainLabel(chain)}
      width={20}
      height={20}
      loading="lazy"
      decoding="async"
      // On the testnet path the caller's className sizes the wrapper instead,
      // so the image just fills it. Merging the two would let tailwind-merge
      // drop `size-full` in favour of the caller's `size-4`.
      // The logo keeps its own colour on the testnet path. The dashed outline
      // carries the network signal without reducing chain recognition.
      className={
        testnet
          ? "size-full rounded-full"
          : cn("size-5 rounded-full", className)
      }
    />
  );

  if (!testnet) return image;

  return (
    // inline-flex, not inline-block: an inline <img> carries a baseline gap
    // that would make this wrapper a few pixels taller than a bare mainnet
    // icon and knock the two out of alignment in adjacent rows.
    <span
      data-slot="chain-icon"
      className={cn(
        "relative inline-flex size-5 shrink-0 rounded-full",
        className,
      )}
    >
      {image}
      {/* Dark dashed outline marking a testnet. Decorative: every call site
       * that passes `network` also renders that network's name as adjacent
       * text, so this only speeds up sighted scanning. Drawn in globals.css. */}
      <span aria-hidden data-slot="chain-testnet-mark" />
    </span>
  );
}
