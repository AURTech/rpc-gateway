import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { GatewayDetailContent } from "../../../../gateways/_components/gateway-detail-content";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({
    locale,
    namespace: "dashboard.gateways",
  });
  return { title: t("page.metaTitle") };
}

/** Per-gateway V2 control-plane page nested under its owning app. */
export default async function GatewayConfigPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string; id: string; gatewayId: string }>;
  searchParams: Promise<{ transport?: string }>;
}) {
  const { id, gatewayId } = await params;
  const { transport } = await searchParams;
  const initialTransport = transport === "http_api" ? "http_api" : "jsonrpc";

  return (
    <div className="flex flex-col gap-7 pt-2">
      <GatewayDetailContent
        appId={id}
        gatewayId={gatewayId}
        initialTransport={initialTransport}
      />
    </div>
  );
}
