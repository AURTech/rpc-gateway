import type { ProviderEndpoint, RpcProviderBase } from "@/api/providers/client";

export interface EndpointCounts {
  present: number;
  missing: number;
}

export type ProviderRecord = RpcProviderBase;

export type ProviderEndpointRecord = ProviderEndpoint;

export function endpointCounts(provider: ProviderRecord): EndpointCounts {
  return provider.endpoint_counts;
}

export function providerStatus(
  provider: ProviderRecord,
): "paused" | "syncing" | "attention" | "never" | "current" {
  if (!provider.enabled) return "paused";
  if (provider.syncing) {
    return "syncing";
  }
  if (
    provider.last_sync_status === "failed" ||
    provider.last_sync_status === "partial"
  ) {
    return "attention";
  }
  if (provider.last_sync_status === "never") return "never";
  return "current";
}

export function endpointDiscovery(item: ProviderEndpointRecord) {
  return item.discovery_status;
}

export function endpointRegistry(item: ProviderEndpointRecord) {
  return item.registry_state;
}
