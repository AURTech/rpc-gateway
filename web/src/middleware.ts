import { NextRequest, NextResponse } from "next/server";
import createMiddleware from "next-intl/middleware";

import { routing } from "@/i18n/routing";
import { authRedirectPath, localeFromPath } from "@/lib/auth-redirect";
import { productionContentSecurityPolicy } from "@/lib/security-headers";

/**
 * Session cookie set by the backend on successful login
 * (server/app/services/auth/session.py::SESSION_COOKIE_NAME). HttpOnly, so we
 * can only test for its *presence* here — real validity is verified client-side
 * via `useAuthIdentity` (GET /v2/auth/me), which bounces stale cookies back
 * to /login.
 */
const SESSION_COOKIE = "rpc_gateway_session";

const intlMiddleware = createMiddleware(routing);

function withContentSecurityPolicy(req: NextRequest): {
  policy: string | null;
  request: NextRequest;
} {
  const isProduction = process.env.NODE_ENV === "production";
  if (!isProduction) return { policy: null, request: req };

  const nonce = crypto.randomUUID();
  const policy = productionContentSecurityPolicy({
    apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL,
    isProduction,
    nonce,
  });
  if (!policy) return { policy: null, request: req };

  const headers = new Headers(req.headers);
  headers.set("Content-Security-Policy", policy);
  headers.set("x-nonce", nonce);
  return { policy, request: new NextRequest(req, { headers }) };
}

function withResponseContentSecurityPolicy(
  response: NextResponse,
  policy: string | null,
): NextResponse {
  if (policy) response.headers.set("Content-Security-Policy", policy);
  return response;
}

function redirectTo(req: NextRequest, path: string): NextResponse {
  const url = req.nextUrl.clone();
  url.pathname = path;
  url.search = "";
  return NextResponse.redirect(url);
}

export function middleware(req: NextRequest): NextResponse {
  const secured = withContentSecurityPolicy(req);
  const request = secured.request;
  const { pathname } = request.nextUrl;
  const hasSession = request.cookies.has(SESSION_COOKIE);

  const pathLocale = localeFromPath(pathname, routing.locales);

  // Unprefixed, non-root paths (e.g. "/dashboard"): let next-intl add the locale
  // prefix first; the redirected request re-enters this proxy and gets
  // guarded with a well-formed prefix.
  if (pathLocale === null && pathname !== "/") {
    return withResponseContentSecurityPolicy(
      intlMiddleware(request),
      secured.policy,
    );
  }

  const redirectPath = authRedirectPath({
    pathname,
    hasSession,
    locales: routing.locales,
    defaultLocale: routing.defaultLocale,
  });
  if (redirectPath) {
    return withResponseContentSecurityPolicy(
      redirectTo(request, redirectPath),
      secured.policy,
    );
  }

  return withResponseContentSecurityPolicy(
    intlMiddleware(request),
    secured.policy,
  );
}

export const config = {
  matcher: ["/", "/((?!api|trpc|_next|_vercel|.*\\..*).*)"],
};
