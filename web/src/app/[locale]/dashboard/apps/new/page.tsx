import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { CreateAppWizard } from "./_components/create-app-wizard";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({
    locale,
    namespace: "dashboard.apps.wizard",
  });
  return { title: t("metaTitle") };
}

export default function NewAppPage() {
  return <CreateAppWizard />;
}
