import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AppSettingsContent } from "./_components/app-settings-content";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "dashboard.apps" });
  return { title: t("settings.metaTitle") };
}

export default async function AppSettingsPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { id } = await params;

  return <AppSettingsContent appId={id} />;
}
