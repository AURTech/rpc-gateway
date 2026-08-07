import { ChainIcon } from "@/components/ui/chain-icon";
import { chainLabel, type RpcChain } from "@/lib/rpc-chain";
import { cn } from "@/lib/utils";

/**
 * Overlapping cluster of chain logos — the "chain group" used to summarize the
 * chains an entity spans (e.g. an app's gateways) in a single tight cell.
 *
 * Icons overlap with a surface-coloured ring so each reads as a separate disc;
 * anything past `max` collapses into a "+N" pill whose `title`/`aria-label`
 * spells out the hidden chains. Input is deduped and capped here, so callers
 * can hand over the raw list. Renders an em dash when empty.
 */
export function ChainGroup({
  chains,
  max = 5,
  className,
}: {
  chains: RpcChain[];
  max?: number;
  className?: string;
}) {
  const unique = [...new Set(chains)];
  if (unique.length === 0) return <span className="text-ink-400">—</span>;

  const visible = unique.slice(0, max);
  const overflow = unique.slice(max);
  const overflowLabels = overflow.map(chainLabel).join(", ");

  return (
    <div
      className={cn("flex items-center -space-x-1.5", className)}
      // The native title gives the full chain list on hover; each icon also
      // carries its own alt text for assistive tech.
      title={unique.map(chainLabel).join(", ")}
    >
      {visible.map((chain) => (
        <ChainIcon key={chain} chain={chain} className="ring-2 ring-surface" />
      ))}
      {overflow.length > 0 ? (
        <span
          role="img"
          aria-label={`+${overflow.length}: ${overflowLabels}`}
          className="inline-flex size-5 items-center justify-center rounded-full bg-table-frame text-2xs font-medium text-ink-500 ring-2 ring-surface"
        >
          +{overflow.length}
        </span>
      ) : null}
    </div>
  );
}
