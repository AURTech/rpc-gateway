import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

interface AuthLayoutProps {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}

export async function generateMetadata({
  params,
}: AuthLayoutProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "auth" });

  return {
    title: t("callback_pending_title"),
    description: t("callback_pending_subtitle"),
  };
}

export default function AuthLayout({ children }: AuthLayoutProps) {
  return children;
}
