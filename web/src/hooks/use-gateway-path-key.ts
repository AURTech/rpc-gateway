"use client";

import { useAppKeysQuery } from "@/hooks/use-apps";

export type GatewayPathKeyStatus =
  | "metadata-loading"
  | "metadata-error"
  | "missing"
  | "available";

export function useGatewayPathKey(appId: string) {
  const {
    data: keys,
    isError,
    isFetching,
    isPending,
    refetch,
  } = useAppKeysQuery(appId);
  const activeKey = keys?.items.find((key) => key.state === "active");

  let status: GatewayPathKeyStatus;
  if (isPending) status = "metadata-loading";
  else if (isError) status = "metadata-error";
  else if (!activeKey) status = "missing";
  else status = "available";

  return {
    pathKey: activeKey?.api_key ?? null,
    status,
    refetchKeys: refetch,
    isRefetchingKeys: isFetching,
  };
}
