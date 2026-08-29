import type { Metadata, Viewport } from "next";

import { siteDescription, siteName, siteTitle, siteUrl } from "@/lib/site";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  applicationName: siteName,
  title: {
    default: siteTitle,
    template: `%s · ${siteName}`,
  },
  description: siteDescription,
  robots: {
    index: false,
    follow: false,
    noarchive: true,
    nocache: true,
    noimageindex: true,
    nosnippet: true,
    googleBot: {
      index: false,
      follow: false,
      noarchive: true,
      noimageindex: true,
      nosnippet: true,
    },
  },
  openGraph: {
    type: "website",
    url: siteUrl,
    siteName,
    title: siteTitle,
    description: siteDescription,
  },
  twitter: {
    card: "summary",
    title: siteTitle,
    description: siteDescription,
  },
  icons: {
    icon: [{ url: "/aurpay-logo.svg", type: "image/svg+xml" }],
    shortcut: "/aurpay-logo.svg",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  colorScheme: "light",
};

// The root layout is a pass-through. `<html>`/`<body>` and providers live in
// `app/[locale]/layout.tsx`, where the active locale is known from route
// params — the only place `lang` can be set correctly under static rendering.
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return children;
}
