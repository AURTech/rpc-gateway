import type { Metadata, Viewport } from "next";

import { siteUrl } from "@/lib/site";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "Gateway · RPC control plane",
    template: "%s · Gateway",
  },
  description: "V2 control plane for apps, gateways, endpoints, and providers.",
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
