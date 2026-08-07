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
 * single (chain, network) pair: a testnet is then muted and laid over with
 * amber hazard tape (see `chain-testnet-mark` in globals.css). Omit it in
 * chain-only contexts (filters, `ChainGroup`) where the icon means "the chain"
 * and a testnet marker would be wrong.
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
      // The logo keeps its own colour on the testnet path. Desaturating it was
      // tried and rejected: it turns TRON brick-brown and Bitcoin tan, which
      // reads as a disabled control rather than a test network, and it costs
      // the chain recognition the logo exists for. The tape carries the
      // signal on its own.
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
      {/* Amber hazard tape marking a testnet — striped rather than a dot or a
       * ring because tape reads as "not the real thing" on sight, where an
       * abstract mark has to be learned. Decorative: every call site that
       * passes `network` also renders that network's name as adjacent text, so
       * the tape speeds up sighted scanning rather than carrying the only copy
       * of the signal. Drawn in globals.css. */}
      <span aria-hidden data-slot="chain-testnet-mark" />
    </span>
  );
}
