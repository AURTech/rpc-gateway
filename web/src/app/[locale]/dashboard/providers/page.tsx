import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { NewProviderButton } from "./_components/new-provider-button";
import { ProvidersContent } from "./_components/providers-content";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "dashboard.providers" });
  return { title: t("metaTitle") };
}

export default async function ProvidersPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ provider?: string }>;
}) {
  const { locale } = await params;
  const { provider } = await searchParams;
  const t = await getTranslations({ locale, namespace: "dashboard.providers" });

  return (
    <div className="flex flex-col gap-7 pt-2">
      <header className="flex flex-wrap items-end justify-between gap-6">
        <div className="flex max-w-prose-narrow flex-col gap-1.5">
          <h1 className="text-3xl font-bold tracking-tight text-ink-900">
            {t("title")}
          </h1>
          <p className="text-md text-ink-500">{t("subtitle")}</p>
        </div>
        <NewProviderButton label={t("cta.newProvider")} />
      </header>
      <ProvidersContent initialProviderId={provider ?? null} />
    </div>
  );
}
