/**
 * Maps a raw `?error=` code (forwarded by the backend OAuth flow) to a key in
 * the `auth` i18n namespace. Returns null when there's no error to show.
 */
export function authErrorKey(code: string | null | undefined): string | null {
  if (!code) return null;
  switch (code) {
    case "access_denied":
      return "auth_error_oauth_denied";
    case "session_invalid":
    case "session_expired":
      return "auth_error_session_invalid";
    case "oauth_failed":
      return "auth_error_oauth_failed";
    default:
      return "auth_error_unknown";
  }
}
