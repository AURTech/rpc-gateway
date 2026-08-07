type BuildEnvironment = Readonly<Record<string, string | undefined>>;

function requiredValue(environment: BuildEnvironment, name: string): string {
  const value = environment[name]?.trim();
  if (!value) {
    throw new Error(`Required production build variable ${name} is not set.`);
  }
  return value;
}

function requireHttpUrl(name: string, value: string): void {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`${name} must be an absolute HTTP(S) URL.`);
  }

  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error(`${name} must be an absolute HTTP(S) URL.`);
  }
}

export function validateProductionBuildEnvironment(
  environment: BuildEnvironment,
): void {
  const apiBaseUrl = requiredValue(environment, "NEXT_PUBLIC_API_BASE_URL");
  const siteUrl = requiredValue(environment, "NEXT_PUBLIC_SITE_URL");

  requireHttpUrl("NEXT_PUBLIC_SITE_URL", siteUrl);

  if (apiBaseUrl === "/api") {
    const proxyTarget = requiredValue(environment, "API_PROXY_TARGET");
    requireHttpUrl("API_PROXY_TARGET", proxyTarget);
    return;
  }

  requireHttpUrl("NEXT_PUBLIC_API_BASE_URL", apiBaseUrl);
}
