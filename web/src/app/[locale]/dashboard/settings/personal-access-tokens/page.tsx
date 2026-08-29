import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { PersonalAccessTokenCard } from "../_components/personal-access-token-card";
import { SettingsPageHeader } from "../_components/settings-page-header";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({
    locale,
    namespace: "dashboard.settings.tokens",
  });
  return { title: t("metaTitle") };
}

export default async function PersonalAccessTokensPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const t = await getTranslations({
    locale,
    namespace: "dashboard.settings.tokens",
  });

  return (
    <>
      <SettingsPageHeader
        title={t("pageTitle")}
        subtitle={t("pageDescription")}
      />
      <PersonalAccessTokenCard />
    </>
  );
}
