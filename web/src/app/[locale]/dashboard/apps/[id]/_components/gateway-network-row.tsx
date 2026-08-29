"use client";

import { ChevronRight, CopyIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import type {
  RpcGatewayBase,
  RpcGatewayTransport,
} from "@/api/gateways/client";
import { MotionListItem } from "@/components/patterns/motion-list";
import { ChainIcon } from "@/components/ui/chain-icon";
import { Link } from "@/i18n/navigation";
import { networkLabel } from "@/lib/rpc-chain";
import { endpointUsesPathKey, fillPathKeyTemplate } from "@/lib/rpc-endpoint";
import { cn } from "@/lib/utils";

import { IconButton } from "../../../_components/compact-drawer";
import { StatePill } from "../../../gateways/_components/gateway-pills";

/**
 * A single (chain, network) gateway row inside the app's networks panel. The
 * network label and the trailing chevron link to the gateway's dedicated config
 * page (`/dashboard/apps/<appId>/gateways/<gatewayId>`). The row surfaces one
 * access point at a time — the protocol chosen in the endpoint column header —
 * with a quick-copy action.
 */
export function GatewayNetworkRow({
  gateway,
  appId,
  transport,
  onCopy,
  onNavigate,
  pathKey = null,
  pathKeyCopyDisabled = false,
}: {
  gateway: RpcGatewayBase;
  appId: string;
  transport: RpcGatewayTransport;
  onCopy: (url: string) => void;
  onNavigate?: () => void;
  pathKey?: string | null;
  pathKeyCopyDisabled?: boolean;
}) {
  const t = useTranslations("dashboard.apps");
  const tg = useTranslations("dashboard.gateways");
  const tn = useTranslations("dashboard.apps.detail.networks");

  const configHref = `/dashboard/apps/${appId}/gateways/${gateway.id}?transport=${transport}`;
  const displayNetwork = networkLabel(gateway.chain, gateway.network);

  const accessPoint =
    gateway.access_points.find((item) => item.transport === transport) ?? null;
  const label = tn(`transport.${transport}`);
  const usesPathKey = accessPoint
    ? endpointUsesPathKey(accessPoint.url)
    : false;
  const displayValue = accessPoint
    ? pathKey && usesPathKey
      ? fillPathKeyTemplate(accessPoint.url, pathKey)
      : accessPoint.url
    : null;

  return (
    <MotionListItem
      as="li"
      className="group flex flex-col gap-2 px-5 py-3 md:grid md:grid-cols-12 md:items-center md:gap-3"
    >
      <div className="col-span-2 flex items-center gap-1.5">
        <ChainIcon
          chain={gateway.chain}
          network={gateway.network}
          className="size-5 shrink-0"
        />
        <Link
          href={configHref}
          onNavigate={onNavigate}
          className="truncate text-md font-medium text-ink-900 transition-colors hover:text-brand"
        >
          {displayNetwork}
        </Link>
      </div>

      {/* The selected protocol's endpoint. A disabled gateway serves no traffic,
       * so the URL reads as inert: muted text and a non-actionable copy. Chains
       * that don't expose the selected protocol show a muted placeholder. */}
      <div className="col-span-8 flex min-w-0 items-center gap-1.5">
        {accessPoint ? (
          <>
            <span
              className={cn(
                "min-w-0 flex-1 truncate font-mono text-sm",
                gateway.effective_enabled ? "text-ink-700" : "text-ink-400",
              )}
            >
              {displayValue}
            </span>
            <IconButton
              ariaLabel={tg("table.copyEndpoint", { name: label })}
              onClick={() => onCopy(displayValue as string)}
              disabled={
                !gateway.effective_enabled ||
                (usesPathKey && pathKeyCopyDisabled)
              }
              className="shrink-0"
            >
              <CopyIcon className="size-3.5" aria-hidden />
            </IconButton>
          </>
        ) : (
          <span className="text-sm text-ink-400">{tn("noEndpoint")}</span>
        )}
      </div>

      <div className="col-span-1">
        <StatePill
          enabled={gateway.effective_enabled}
          enabledLabel={t("status.enabled")}
          disabledLabel={t("status.disabled")}
        />
      </div>

      <div className="col-span-1 flex items-center md:justify-end">
        <Link
          href={configHref}
          onNavigate={onNavigate}
          aria-label={tg("actions.configure")}
          className="inline-flex size-8 items-center justify-center rounded-md text-ink-500 transition-colors hover:bg-ink-wash hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
        >
          <ChevronRight className="size-4" aria-hidden />
        </Link>
      </div>
    </MotionListItem>
  );
}
