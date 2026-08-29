import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  locales: ["en"],
  defaultLocale: "en",
  // The console is English-only, but every page keeps its locale prefix so the
  // canonical path stays `/en/...`.
  localePrefix: "always",
  localeDetection: false,
});
