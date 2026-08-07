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

  const document = getLegalDocument("terms", locale);
  return {
    title: document.title,
    description: document.description,
    alternates: {
      canonical: `/${locale}/terms`,
      languages: { en: "/en/terms" },
    },
  };
}

export default async function TermsPage({ params }: LegalPageProps) {
  const { locale } = await params;
  if (!isLegalLocale(locale)) notFound();

  return (
    <LegalPage document={getLegalDocument("terms", locale)} locale={locale} />
  );
}
