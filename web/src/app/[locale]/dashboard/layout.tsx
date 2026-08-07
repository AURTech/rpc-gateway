import { setRequestLocale } from "next-intl/server";
import type { ReactNode } from "react";

import { DashboardShell } from "./_components/dashboard-shell";

export default async function DashboardLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  return <DashboardShell>{children}</DashboardShell>;
}
