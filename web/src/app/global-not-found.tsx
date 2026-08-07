import type { Metadata } from "next";

import { GeistSans } from "@/app/fonts";
import { NotFoundPage } from "@/components/not-found-page";
import "./globals.css";

export const metadata: Metadata = {
  title: "404 - Page not found",
  description: "The requested page does not exist.",
};

export default function GlobalNotFound() {
  return (
    <html lang="en" className={GeistSans.variable} suppressHydrationWarning>
      <body className="antialiased font-sans">
        <NotFoundPage
          statusLabel="404"
          eyebrow="Route not found"
          title="Page not found"
          description="This address does not match any active Gateway console page. The page may have been removed, renamed, or copied incorrectly."
          primaryHref="/en/dashboard"
          primaryLabel="Open dashboard"
          secondaryHref="/en/login"
          secondaryLabel="Sign in"
          guidanceTitle="Try a known console entry"
          guidanceDescription="Use one of these routes instead of retrying the same address."
          routeHint="No active app route matched this URL."
          bookmarkHint="Update saved bookmarks to the dashboard route after opening the right page."
          quickLinks={[
            {
              href: "/en/dashboard/apps",
              label: "Apps",
              description: "Manage RPC apps and keys.",
              icon: "apps",
            },
            {
              href: "/en/dashboard/providers",
              label: "Providers",
              description: "Manage provider connections.",
              icon: "providers",
            },
            {
              href: "/en/dashboard/endpoints",
              label: "Endpoints",
              description: "Manage endpoint connections.",
              icon: "endpoints",
            },
            {
              href: "/en/dashboard/settings",
              label: "Settings",
              description: "Open account preferences.",
              icon: "settings",
            },
          ]}
        />
      </body>
    </html>
  );
}
