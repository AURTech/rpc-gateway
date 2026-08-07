import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AppOverviewContent } from "./_components/app-overview-content";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({
    locale,
    namespace: "dashboard.apps",
  });
  return { title: t("detail.overviewMetaTitle") };
}

export default async function AppOverviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string; id: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  const { id } = await params;
  const { tab } = await searchParams;

  // Leave `initialTab` undefined when the URL said nothing, so the content can
  // tell "show me setup" apart from "pick a default for me".
  const initialTab =
    tab === "gateways" ? "gateways" : tab === "setup" ? "setup" : undefined;

  return (
    <div className="flex flex-col gap-7 pt-2">
      <AppOverviewContent appId={id} initialTab={initialTab} />
    </div>
  );
}
