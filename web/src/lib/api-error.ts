import { type ApiError, isApiError } from "@/api/client";

/**
 * Minimal structural translator. Compatible with next-intl's
 * `useTranslations("errors")` return value, but decoupled for testing.
 */
type ErrorTranslator = (key: string) => string;

/** Keys live under the `errors` namespace in locales/<lng>/common.json. */
type ErrorKey =
  | "offline"
  | "timeout"
  | "server"
  | "unauthorized"
  | "forbidden"
  | "notFound"
  | "generic";

function errorKeyFor(error: ApiError): ErrorKey {
  if (error.kind === "network") return "offline";
  if (error.kind === "timeout") return "timeout";
  if (error.isServer) return "server";
  if (error.isUnauthorized) return "unauthorized";
  if (error.isForbidden) return "forbidden";
  if (error.isNotFound) return "notFound";
  return "generic";
}

/**
 * Resolve a user-facing message for any thrown value.
 *
 * Prefers the backend's human-readable `msg` (already localized server-side and
 * including aggregated 422 validation text); otherwise falls back to a
 * translated message keyed by the failure kind / HTTP status.
 *
 * `t` must be bound to the `errors` namespace, e.g. `useTranslations("errors")`.
 */
export function getApiErrorMessage(error: unknown, t: ErrorTranslator): string {
  if (isApiError(error)) {
    // Backend-supplied message: only HTTP errors carry a real body.
    if (error.kind === "http" && typeof error.data === "object") {
      const msg = (error.data as { msg?: unknown } | null)?.msg;
      if (typeof msg === "string" && msg.trim()) return msg;
    }
    return t(errorKeyFor(error));
  }
  return t("generic");
}

/** True when the failure is an unauthenticated (401) API response. */
export function isAuthError(error: unknown): boolean {
  return isApiError(error) && error.isUnauthorized;
}
