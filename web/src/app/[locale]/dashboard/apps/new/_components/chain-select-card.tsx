"use client";

import { CheckIcon } from "lucide-react";

import { ChainIcon } from "@/components/ui/chain-icon";
import {
  chainAccent,
  chainLabel,
  networkLabel,
  RPC_CHAIN_REGISTRY,
} from "@/lib/rpc-chain";
import { cn } from "@/lib/utils";

import { type ChainCatalogGroup, networkKey } from "./chain-catalog";

/**
 * One selectable chain in the create-app wizard's network step. The whole card
 * is the "select this chain" control: the header button stretches its hit area
 * across the card, so a click anywhere outside a pill toggles every network on
 * if any is off, otherwise all off. The whole card tints and picks up a brand
 * ring on hover to advertise that reach, and turns to a solid brand ring once
 * any of its networks is on, so a filled card reads as "this chain is in". The
 * network pills stack above the overlay and stay individually toggleable for
 * fine-grained picks. Selection is keyed by (chain, network) — see
 * {@link networkKey} — because the app, and so its gateways, doesn't exist
 * until the wizard finishes.
 */
export function ChainSelectCard({
  group,
  selected,
  onToggleNetwork,
  onToggleChain,
}: {
  group: ChainCatalogGroup;
  selected: ReadonlySet<string>;
  onToggleNetwork: (key: string) => void;
  onToggleChain: (keys: string[]) => void;
}) {
  const keys = group.networks.map((network) =>
    networkKey(group.chain, network),
  );
  const active = keys.some((key) => selected.has(key));
  const accent = chainAccent(group.chain);

  return (
    <div
      data-active={active}
      className={cn(
        // Hover reads as a background tint plus a brand ring, not a drop
        // shadow: the grid gap is narrower than an elevated shadow's blur, so
        // lifting a card would smear onto its neighbours and the footer bar
        // below. `ring` is inset and the tint is clipped to the card, so both
        // stay inside its own box. `ring` compiles to a box-shadow, hence
        // transitioning shadow alongside colors.
        "relative flex flex-col gap-4 rounded-2xl bg-surface p-4 shadow-card ring-1 ring-inset transition-[background-color,box-shadow] hover:bg-row-hover",
        active ? "ring-brand/40" : "ring-table-frame hover:ring-brand/30",
      )}
    >
      <button
        type="button"
        onClick={() => onToggleChain(keys)}
        aria-pressed={active}
        aria-label={chainLabel(group.chain)}
        // The `before` overlay stretches this button over the whole card, so
        // the card-wide hover affordance matches a card-wide hit area.
        className="-m-1 flex items-center gap-3 rounded-xl p-1 text-left before:absolute before:inset-0 before:rounded-2xl before:content-[''] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        <span
          aria-hidden
          className="inline-flex size-10 shrink-0 items-center justify-center rounded-full"
          // Tint the logo backdrop with the chain's colour at ~10% so each card
          // carries a splash of its identity without bundled art. Mixed rather
          // than alpha-suffixed: `accent` is a `var(--chain-*)` reference, not a
          // literal hex we could append an alpha pair to.
          style={{
            backgroundColor: `color-mix(in oklab, ${accent} 10%, transparent)`,
          }}
        >
          <ChainIcon chain={group.chain} className="size-6" />
        </span>
        <div className="flex min-w-0 flex-col">
          <span className="truncate text-md font-semibold text-ink-900">
            {chainLabel(group.chain)}
          </span>
          <span className="text-xs font-medium uppercase tracking-wide text-ink-400">
            {RPC_CHAIN_REGISTRY[group.chain].short}
          </span>
        </div>
      </button>

      {/* Raised above the header button's stretched overlay so the pills keep
          their own clicks. */}
      <div className="relative flex flex-wrap gap-2">
        {group.networks.map((network) => {
          const key = networkKey(group.chain, network);
          const on = selected.has(key);
          return (
            <button
              key={key}
              type="button"
              onClick={() => onToggleNetwork(key)}
              aria-pressed={on}
              aria-label={`${chainLabel(group.chain)} ${networkLabel(group.chain, network)}`}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-medium transition-colors",
                on
                  ? // Selected pills hover too, so "click again to drop it" stays
                    // discoverable.
                    "border-brand bg-brand-soft text-brand hover:border-brand-hover hover:text-brand-hover"
                  : "border-table-frame bg-surface text-ink-500 hover:border-brand/40 hover:text-ink-800",
              )}
            >
              {on ? <CheckIcon className="size-3.5" aria-hidden /> : null}
              {networkLabel(group.chain, network)}
            </button>
          );
        })}
      </div>
    </div>
  );
}
