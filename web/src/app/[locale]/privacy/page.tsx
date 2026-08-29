import type { Metadata } from "next";

import { LegalPage } from "@/app/[locale]/_components/legal-page";
import { getLegalDocument } from "@/lib/legal-documents";

const privacyDocument = getLegalDocument("privacy");

export const metadata: Metadata = {
  title: privacyDocument.title,
  description: privacyDocument.description,
  alternates: {
    canonical: "/en/privacy",
  },
};

export default function PrivacyPage() {
  return <LegalPage document={privacyDocument} />;
}
