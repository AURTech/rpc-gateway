import type { Metadata } from "next";

import { LegalPage } from "@/app/[locale]/_components/legal-page";
import { getLegalDocument } from "@/lib/legal-documents";

const termsDocument = getLegalDocument("terms");

export const metadata: Metadata = {
  title: termsDocument.title,
  description: termsDocument.description,
  alternates: {
    canonical: "/en/terms",
  },
};

export default function TermsPage() {
  return <LegalPage document={termsDocument} />;
}
