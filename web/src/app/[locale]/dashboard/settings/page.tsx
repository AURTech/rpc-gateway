import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { DangerSection } from "./_components/danger-section";
import { ProfileSection } from "./_components/profile-section";
import { SettingsPageHeader } from "./_components/settings-page-header";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({
    locale,
    namespace: "dashboard.settings.profile",
  });
  return { title: t("metaTitle") };
}

export default async function SettingsProfilePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const t = await getTranslations({
    locale,
    namespace: "dashboard.settings.profile",
  });

  return (
    <>
      <SettingsPageHeader title={t("title")} subtitle={t("subtitle")} />
      <div className="flex flex-col gap-7">
        <ProfileSection />
        <DangerSection />
      </div>
    </>
  );
}
