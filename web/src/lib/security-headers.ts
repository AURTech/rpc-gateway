export const FIXED_SECURITY_HEADERS = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value:
      "camera=(), geolocation=(), microphone=(), payment=(), usb=(), browsing-topics=()",
  },
  { key: "X-XSS-Protection", value: "0" },
] as const;

export const HSTS_HEADER = {
  key: "Strict-Transport-Security",
  value: "max-age=31536000; includeSubDomains",
} as const;

function absoluteHttpOrigin(value: string | undefined): string | null {
  if (!value) return null;

  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:"
      ? url.origin
      : null;
  } catch {
    return null;
  }
}

export function buildContentSecurityPolicy(options: {
  apiBaseUrl?: string;
  nonce: string;
}): string {
  const apiOrigin = absoluteHttpOrigin(options.apiBaseUrl);
  const connectSources = ["'self'", ...(apiOrigin ? [apiOrigin] : [])];

  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${options.nonce}'`,
    "script-src-attr 'none'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https:",
    "font-src 'self' data:",
    `connect-src ${connectSources.join(" ")}`,
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "upgrade-insecure-requests",
  ].join("; ");
}

export function productionContentSecurityPolicy(options: {
  apiBaseUrl?: string;
  isProduction: boolean;
  nonce: string;
}): string | null {
  if (!options.isProduction) return null;
  return buildContentSecurityPolicy(options);
}
