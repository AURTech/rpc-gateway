import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { LegalPage } from "@/app/[locale]/_components/legal-page";
import { getLegalDocument, isLegalLocale } from "@/lib/legal-documents";

interface LegalPageProps {
  params: Promise<{ locale: string }>;
}

export async function generateMetadata({
  params,
}: LegalPageProps): Promise<Metadata> {
  const { locale } = await params;
  if (!isLegalLocale(locale)) return {};

  const document = getLegalDocument("privacy", locale);
  return {
    title: document.title,
    description: document.description,
    alternates: {
      canonical: `/${locale}/privacy`,
      languages: { en: "/en/privacy" },
    },
  };
}

export default async function PrivacyPage({ params }: LegalPageProps) {
  const { locale } = await params;
  if (!isLegalLocale(locale)) notFound();

  return (
    <LegalPage document={getLegalDocument("privacy", locale)} locale={locale} />
  );
}
