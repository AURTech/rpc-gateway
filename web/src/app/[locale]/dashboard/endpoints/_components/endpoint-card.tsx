"use client";

import { useTranslations } from "next-intl";

import type { Endpoint } from "@/api/endpoints/client";
import { Badge } from "@/components/ui/badge";
import { ChainIcon } from "@/components/ui/chain-icon";
import { Checkbox } from "@/components/ui/checkbox";

import { EndpointSourceTags } from "./endpoint-source-tags";

/**
 * One endpoint rendered as a card — the mobile counterpart to the desktop
 * {@link EndpointRow}. Shows name, state, chain/network/protocol, and origin.
 */
export function EndpointCard({
  endpoint,
  selectable = false,
  selected = false,
  onSelect,
}: {
  endpoint: Endpoint;
  selectable?: boolean;
  selected?: boolean;
  onSelect?: (endpoint: Endpoint) => void;
}) {
  const t = useTranslations("dashboard.endpoints");

  return (
    <div className="flex flex-col gap-3 rounded-2xl bg-surface p-4 shadow-card">
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          {selectable ? (
            <Checkbox
              checked={selected}
              onCheckedChange={() => onSelect?.(endpoint)}
              aria-label={t("bulk.selectEndpoint", { name: endpoint.name })}
            />
          ) : null}
          <ChainIcon
            chain={endpoint.chain}
            network={endpoint.network}
            className="size-5 shrink-0"
          />
          <span className="truncate text-md font-semibold text-ink-900">
            {endpoint.name}
          </span>
        </div>
        <Badge dot variant={endpoint.enabled ? "positive" : "neutral"}>
          {endpoint.enabled ? t("state.enabled") : t("state.disabled")}
        </Badge>
      </div>

      <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-sm text-ink-500">
        <span className="text-ink-700">{t(`chain.${endpoint.chain}`)}</span>
        <span aria-hidden>·</span>
        <span>{t(`network.${endpoint.network}`)}</span>
        <span aria-hidden>·</span>
        <span>{t(`protocol.${endpoint.protocol}`)}</span>
      </div>

      <EndpointSourceTags endpoint={endpoint} />
    </div>
  );
}
