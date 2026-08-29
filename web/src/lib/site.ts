export const siteName = "RPC Gateway";
export const siteTitle = "RPC Gateway Console";
export const siteDescription =
  "Control plane for RPC apps, gateways, endpoints, and providers.";

/**
 * Canonical public origin used for metadataBase and social metadata. Override
 * per environment via NEXT_PUBLIC_SITE_URL; falls back to the local dev origin
 * so absolute URLs resolve in development.
 */
export const siteUrl =
  process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:19341";
