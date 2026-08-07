const LOCAL_API_BASE_URL = "http://localhost:18173";

export function getApiBaseUrl() {
  return (process.env.NEXT_PUBLIC_API_BASE_URL || LOCAL_API_BASE_URL).replace(
    /\/$/,
    "",
  );
}
