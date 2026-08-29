import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { EndpointManagementWorkspace } from "./_components/endpoint-management-workspace";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "dashboard.endpoints" });
  return { title: t("metaTitle") };
}

export default async function EndpointsPage({
  searchParams,
}: {
  searchParams: Promise<{ workspace?: string }>;
}) {
  const { workspace } = await searchParams;
  return (
    <EndpointManagementWorkspace
      initialView={workspace === "providers" ? "providers" : "registry"}
    />
  );
}
