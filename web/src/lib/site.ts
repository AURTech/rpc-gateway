/**
 * Canonical public origin used for metadataBase, canonical URLs and OG tags.
 * Override per environment via NEXT_PUBLIC_SITE_URL; falls back to the local
 * dev origin so absolute URLs resolve in development.
 */
export const siteUrl =
  process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:19341";
