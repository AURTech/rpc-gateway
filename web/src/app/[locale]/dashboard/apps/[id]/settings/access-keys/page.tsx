import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AppKeyManagement } from "../_components/app-key-management";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({
    locale,
    namespace: "dashboard.apps.settings.keys",
  });
  return { title: t("title") };
}

export default async function AppAccessKeysPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { id } = await params;

  return <AppKeyManagement appId={id} />;
}
