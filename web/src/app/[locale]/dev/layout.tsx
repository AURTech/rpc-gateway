import { notFound } from "next/navigation";
import { setRequestLocale } from "next-intl/server";
import type { ReactNode } from "react";

/**
 * Dev-only section gate. Mirrors the `NODE_ENV` guard used for React Query
 * Devtools in `providers.tsx`: everything under `/dev` returns 404 in
 * production builds, so the component gallery never ships to users.
 */
export default async function DevLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <div className="min-h-screen bg-page-bg font-sans text-ink-900">
      {children}
    </div>
  );
}
