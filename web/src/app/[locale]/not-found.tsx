import { getLocale, getTranslations } from "next-intl/server";

import { NotFoundPage } from "@/components/not-found-page";

export default async function NotFound() {
  const locale = await getLocale();
  const t = await getTranslations("notFoundPage");

  return (
    <NotFoundPage
      statusLabel="404"
      eyebrow={t("eyebrow")}
      title={t("title")}
      description={t("description")}
      primaryHref={`/${locale}/dashboard`}
      primaryLabel={t("primary")}
      secondaryHref={`/${locale}/login`}
      secondaryLabel={t("secondary")}
      guidanceTitle={t("guidanceTitle")}
      guidanceDescription={t("guidanceDescription")}
      routeHint={t("routeHint")}
      bookmarkHint={t("bookmarkHint")}
      quickLinks={[
        {
          href: `/${locale}/dashboard/apps`,
          label: t("links.apps.label"),
          description: t("links.apps.description"),
          icon: "apps",
        },
        {
          href: `/${locale}/dashboard/providers`,
          label: t("links.providers.label"),
          description: t("links.providers.description"),
          icon: "providers",
        },
        {
          href: `/${locale}/dashboard/endpoints`,
          label: t("links.endpoints.label"),
          description: t("links.endpoints.description"),
          icon: "endpoints",
        },
        {
          href: `/${locale}/dashboard/settings`,
          label: t("links.settings.label"),
          description: t("links.settings.description"),
          icon: "settings",
        },
      ]}
    />
  );
}
