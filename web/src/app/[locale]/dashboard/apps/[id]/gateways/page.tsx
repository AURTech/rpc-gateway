import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AppGatewaysContent } from "../_components/app-gateways-content";

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
  return { title: t("detail.metaTitle") };
}

export default async function AppGatewaysPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { id } = await params;

  return (
    <div className="flex flex-col gap-7 pt-2">
      <AppGatewaysContent appId={id} />
    </div>
  );
}
