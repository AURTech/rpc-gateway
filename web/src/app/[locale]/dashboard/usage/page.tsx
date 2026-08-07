import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { UsageContent } from "./_components/usage-content";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({
    locale,
    namespace: "dashboard.usage",
  });
  return { title: t("metaTitle") };
}

export default async function UsagePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const t = await getTranslations({
    locale,
    namespace: "dashboard.usage",
  });

  return (
    <div className="flex flex-col gap-7 pt-2">
      <header className="flex max-w-prose-narrow flex-col gap-1.5">
        <h1 className="text-3xl font-bold tracking-tight text-ink-900">
          {t("title")}
        </h1>
        <p className="text-md text-ink-500">{t("subtitle")}</p>
      </header>

      <UsageContent />
    </div>
  );
}
