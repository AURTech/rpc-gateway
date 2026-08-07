import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { hasLocale } from "next-intl";
import { setRequestLocale } from "next-intl/server";

import { GeistSans } from "@/app/fonts";
import { Providers } from "@/app/providers";
import { loadMessages } from "@/i18n/messages";
import { routing } from "@/i18n/routing";

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;

  if (!hasLocale(routing.locales, locale)) {
    notFound();
  }

  setRequestLocale(locale);
  const messages = await loadMessages();
  const nonce = (await headers()).get("x-nonce") ?? undefined;

  return (
    <html lang={locale} className={GeistSans.variable} suppressHydrationWarning>
      <body className="antialiased font-sans">
        <Providers locale={locale} messages={messages} nonce={nonce}>
          {children}
        </Providers>
      </body>
    </html>
  );
}
