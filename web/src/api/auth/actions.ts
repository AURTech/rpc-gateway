import { getApiBaseUrl } from "@/api/base-url";

export function getGoogleLoginUrl() {
  return `${getApiBaseUrl()}/v2/auth/google/login`;
}

export function getAurPayLoginUrl(
  options: { prompt?: "login" | "select_account" } = {},
) {
  const url = `${getApiBaseUrl()}/v2/auth/aurpay/login`;
  return options.prompt ? `${url}?prompt=${options.prompt}` : url;
}
