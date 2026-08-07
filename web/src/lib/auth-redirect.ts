interface AuthRedirectParams<Locale extends string> {
  pathname: string;
  hasSession: boolean;
  locales: readonly Locale[];
  defaultLocale: Locale;
}

export function localeFromPath<Locale extends string>(
  pathname: string,
  locales: readonly Locale[],
): Locale | null {
  const segment = pathname.split("/")[1];
  return locales.includes(segment as Locale) ? (segment as Locale) : null;
}

export function authRedirectPath<Locale extends string>({
  pathname,
  hasSession,
  locales,
  defaultLocale,
}: AuthRedirectParams<Locale>): string | null {
  const pathLocale = localeFromPath(pathname, locales);
  if (pathLocale === null && pathname !== "/") {
    return null;
  }

  const locale = pathLocale ?? defaultLocale;
  const prefix = `/${locale}`;
  const rest = pathname === prefix ? "" : pathname.slice(prefix.length);

  const isRoot = pathname === "/" || pathname === prefix;
  const isDashboard = rest === "/dashboard" || rest.startsWith("/dashboard/");

  if (rest === "/auth/callback") {
    return null;
  }

  if (isRoot) {
    return hasSession ? `${prefix}/dashboard` : `${prefix}/login`;
  }

  if (isDashboard && !hasSession) {
    return `${prefix}/login`;
  }

  return null;
}
