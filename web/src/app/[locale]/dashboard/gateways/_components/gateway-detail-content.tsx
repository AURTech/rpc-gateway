"use client";

import { ChevronLeftIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import type { RpcGatewayTransport } from "@/api/gateways/client";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { useGatewayQuery } from "@/hooks/use-gateways";
import { Link, usePathname, useRouter } from "@/i18n/navigation";

import { GatewayHeader } from "./gateway-header";
import { GatewayRoutingSection } from "./gateway-routing-section";
import { HttpApiRoutingSection } from "./http-api-routing-section";

type ConfigurableTransport = Extract<
  RpcGatewayTransport,
  "jsonrpc" | "http_api"
>;

/**
 * v2 Gateway detail: a state-aware header above a protocol-aware routing card.
 * JSON-RPC includes per-method rules; HTTP API exposes its gateway-wide route.
 */
export function GatewayDetailContent({
  appId,
  gatewayId,
  initialTransport,
}: {
  appId: string;
  gatewayId: string;
  initialTransport: ConfigurableTransport;
}) {
  const t = useTranslations("dashboard.gateways");
  const pathname = usePathname();
  const router = useRouter();
  const [transportChoice, setTransportChoice] =
    useState<ConfigurableTransport>(initialTransport);

  useEffect(() => {
    setTransportChoice(initialTransport);
  }, [initialTransport]);
  const {
    data: gateway,
    isLoading,
    isError,
    refetch,
  } = useGatewayQuery(gatewayId);
  const backHref = `/dashboard/apps/${appId}/gateways`;

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-4 w-20" />
        <div className="flex items-center justify-between gap-4">
          <Skeleton className="h-9 w-64 max-w-full" />
          <Skeleton className="h-6 w-24" />
        </div>
        <Skeleton className="h-96 w-full rounded-2xl" />
      </div>
    );
  }

  if (isError || !gateway || gateway.app_id !== appId) {
    return (
      <div className="flex flex-col gap-6">
        <Link
          href={backHref}
          aria-label={t("page.back")}
          className="-ml-1 inline-flex w-fit items-center gap-1 text-sm text-ink-500 transition-colors hover:text-brand"
        >
          <ChevronLeftIcon className="size-4" aria-hidden />
          {t("page.back")}
        </Link>
        <div
          role="alert"
          className="mx-auto flex max-w-prose-narrow flex-col items-center gap-2 py-14 text-center"
        >
          <p className="text-lg font-semibold text-ink-900">
            {t("page.notFoundTitle")}
          </p>
          <p className="text-md text-ink-500">{t("page.notFoundBody")}</p>
          <button
            type="button"
            onClick={() => refetch()}
            className="mt-2 inline-flex h-9 items-center rounded-md bg-brand-soft px-4 text-sm font-semibold text-brand transition-colors hover:bg-brand hover:text-white"
          >
            {t("error.retry")}
          </button>
        </div>
      </div>
    );
  }

  const transportOptions = (["jsonrpc", "http_api"] as const).filter(
    (transport) =>
      gateway.access_points.some((point) => point.transport === transport),
  );
  const transport = transportOptions.includes(transportChoice)
    ? transportChoice
    : (transportOptions[0] ?? "jsonrpc");

  const changeTransport = (next: ConfigurableTransport) => {
    setTransportChoice(next);
    router.replace(`${pathname}?transport=${next}`);
  };

  return (
    <div className="flex flex-col gap-6">
      <GatewayHeader gateway={gateway} backHref={backHref} />

      {transportOptions.length > 1 ? (
        <Tabs
          mode="tab"
          value={transport}
          onChange={changeTransport}
          options={transportOptions.map((value) => ({
            value,
            label: t(`apiTypes.${value === "http_api" ? "httpapi" : value}`),
          }))}
          ariaLabel={t("page.protocolLabel")}
          idBase="gateway-transport"
          size="lg"
          variant="underline"
        />
      ) : null}

      <div
        id="gateway-transport-panel"
        role="tabpanel"
        aria-labelledby={
          transportOptions.length > 1
            ? `gateway-transport-${transport}`
            : undefined
        }
        className="rounded-2xl bg-surface p-5 shadow-section md:p-6"
      >
        {transport === "http_api" ? (
          <HttpApiRoutingSection gateway={gateway} />
        ) : (
          <GatewayRoutingSection gateway={gateway} />
        )}
      </div>
    </div>
  );
}
