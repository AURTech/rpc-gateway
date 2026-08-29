"use client";

import { useTranslations } from "next-intl";

import { providerNetworksForVendor } from "@/api/providers/capabilities";
import type {
  RpcProviderNetworkPair,
  RpcProviderVendor,
} from "@/api/providers/client";
import { Badge } from "@/components/ui/badge";
import { ChainGroup } from "@/components/ui/chain-group";
import { ChainIcon } from "@/components/ui/chain-icon";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { chainLabel, networkLabel } from "@/lib/rpc-chain";

const MAX_VISIBLE_NETWORKS = 5;

function uniqueNetworks(
  networks: RpcProviderNetworkPair[] | null,
): RpcProviderNetworkPair[] {
  if (!networks?.length) return [];

  const seen = new Set<string>();
  return networks.filter((pair) => {
    const key = `${pair.chain}:${pair.network}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function pairLabel(pair: RpcProviderNetworkPair): string {
  return `${chainLabel(pair.chain)} · ${networkLabel(pair.chain, pair.network)}`;
}

function NetworkTooltipContent({
  networks,
}: {
  networks: RpcProviderNetworkPair[];
}) {
  const t = useTranslations("dashboard.endpointProviders.networks");

  if (networks.length === 0) return <span>{t("all")}</span>;

  return (
    <ul className="space-y-1.5 py-0.5">
      {networks.map((pair) => (
        <li
          key={`${pair.chain}:${pair.network}`}
          className="flex items-center gap-2 whitespace-nowrap"
        >
          <ChainIcon
            chain={pair.chain}
            network={pair.network}
            className="size-3.5 shrink-0"
          />
          <span>{pairLabel(pair)}</span>
        </li>
      ))}
    </ul>
  );
}

export function ProviderNetworkIconGroup({
  networks,
  vendor,
}: {
  networks: RpcProviderNetworkPair[] | null;
  vendor: RpcProviderVendor;
}) {
  const t = useTranslations("dashboard.endpointProviders.networks");
  const allNetworks = !networks?.length;
  const unique = uniqueNetworks(
    allNetworks ? providerNetworksForVendor(vendor) : networks,
  );
  const visible = unique.slice(0, MAX_VISIBLE_NETWORKS);
  const overflow = unique.length - visible.length;
  const accessibleLabel = allNetworks
    ? `${t("all")}: ${unique.map(pairLabel).join(", ")}`
    : unique.map(pairLabel).join(", ");

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={accessibleLabel}
          className="inline-flex w-fit items-center rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
        >
          {allNetworks ? (
            <ChainGroup chains={unique.map((pair) => pair.chain)} />
          ) : visible.length > 0 ? (
            <span className="flex items-center -space-x-1.5">
              {visible.map((pair) => (
                <span
                  key={`${pair.chain}:${pair.network}`}
                  aria-hidden
                  className="inline-flex rounded-full ring-2 ring-surface"
                >
                  <ChainIcon
                    chain={pair.chain}
                    network={pair.network}
                    className="size-5 shrink-0"
                  />
                </span>
              ))}
              {overflow > 0 ? (
                <span
                  aria-hidden
                  className="inline-flex size-5 items-center justify-center rounded-full bg-table-frame text-2xs font-semibold tabular-nums text-ink-500 ring-2 ring-surface"
                >
                  +{overflow}
                </span>
              ) : null}
            </span>
          ) : null}
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-sm">
        <NetworkTooltipContent networks={allNetworks ? [] : unique} />
      </TooltipContent>
    </Tooltip>
  );
}

export function ProviderNetworkChips({
  networks,
  vendor,
}: {
  networks: RpcProviderNetworkPair[] | null;
  vendor: RpcProviderVendor;
}) {
  const unique = uniqueNetworks(networks ?? providerNetworksForVendor(vendor));

  return (
    <span className="flex flex-wrap gap-1.5">
      {unique.map((pair) => (
        <Badge
          key={`${pair.chain}:${pair.network}`}
          variant="neutral"
          className="gap-1.5 bg-ink-wash text-ink-700"
        >
          <ChainIcon
            chain={pair.chain}
            network={pair.network}
            className="size-3.5 shrink-0"
          />
          {pairLabel(pair)}
        </Badge>
      ))}
    </span>
  );
}
