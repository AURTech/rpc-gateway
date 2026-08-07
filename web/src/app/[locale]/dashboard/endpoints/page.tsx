import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { EndpointsView } from "./_components/endpoints-view";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "dashboard.endpoints" });
  return { title: t("metaTitle") };
}

export default async function EndpointsPage({
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ tab?: string; provider?: string }>;
}) {
  const { tab, provider } = await searchParams;
  // A `?provider=` deep link (from the provider drawer) is only meaningful on
  // the provider-synced tab, so it selects that tab regardless of `?tab=`.
  const initialTab = provider || tab === "provider" ? "provider" : "manual";
  return (
    <EndpointsView
      initialTab={initialTab}
      initialProviderId={provider ?? null}
    />
  );
}
