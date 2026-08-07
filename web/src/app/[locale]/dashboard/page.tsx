import { getTranslations } from "next-intl/server";

import { OverviewAppsPanel } from "./_components/overview-apps-panel";
import { OverviewChartsSection } from "./_components/overview-charts-section";
import { OverviewResourcesCard } from "./_components/overview-resources-card";

export default async function OverviewPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "dashboard.overview" });

  return (
    <div className="flex flex-col gap-7 pt-2">
      <header className="flex flex-col gap-1.5">
        <h1 className="text-3xl font-bold tracking-tight text-ink-900">
          {t("title")}
        </h1>
        <p className="max-w-prose-narrow text-md text-ink-500">
          {t("subhead")}
        </p>
      </header>

      <div className="flex flex-col gap-4 lg:flex-row">
        <OverviewAppsPanel className="min-w-0 flex-1" />
        <OverviewResourcesCard className="lg:w-80 lg:shrink-0" />
      </div>

      <OverviewChartsSection />
    </div>
  );
}
