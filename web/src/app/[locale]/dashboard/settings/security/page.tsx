import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { PersonalAccessTokenCard } from "../_components/personal-access-token-card";
import { SetPasswordCard } from "../_components/set-password-card";
import { SettingsPageHeader } from "../_components/settings-page-header";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({
    locale,
    namespace: "dashboard.settings.security",
  });
  return { title: t("metaTitle") };
}

export default async function SettingsSecurityPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const t = await getTranslations({
    locale,
    namespace: "dashboard.settings.security",
  });

  return (
    <>
      <SettingsPageHeader title={t("title")} subtitle={t("subtitle")} />
      <SetPasswordCard />
      <PersonalAccessTokenCard />
    </>
  );
}
