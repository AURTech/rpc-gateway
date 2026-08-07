import { getApiBaseUrl } from "@/api/base-url";

export function getGoogleLoginUrl() {
  return `${getApiBaseUrl()}/v2/auth/google/login`;
}
