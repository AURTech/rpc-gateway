import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AdminDashboardGuard } from "../_components/admin-dashboard-guard";
import { AccountsContent } from "./_components/accounts-content";
import { NewAccountButton } from "./_components/new-account-button";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({
    locale,
    namespace: "dashboard.admin.accounts",
  });
  return { title: t("metaTitle") };
}

export default async function AccountsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const t = await getTranslations({
    locale,
    namespace: "dashboard.admin.accounts",
  });

  return (
    <AdminDashboardGuard>
      <div className="flex flex-col gap-7 pt-2">
        <header className="flex flex-wrap items-end justify-between gap-6">
          <div className="flex max-w-prose-narrow flex-col gap-1.5">
            <h1 className="text-3xl font-bold tracking-tight text-ink-900">
              {t("title")}
            </h1>
            <p className="text-md text-ink-500">{t("subtitle")}</p>
          </div>
          <NewAccountButton label={t("cta.newAccount")} />
        </header>

        <AccountsContent />
      </div>
    </AdminDashboardGuard>
  );
}
