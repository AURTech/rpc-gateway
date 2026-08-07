"use client";

import { AppDetailFrame } from "./app-detail-frame";
import { AppNetworksPanel } from "./app-networks-panel";
import { GatewayApiKeyCopy } from "./gateway-api-key-copy";
import { useGatewayPathKey } from "./use-gateway-path-key";

/**
 * App "Gateways" sub-page: the shared app header followed by the per-network
 * gateway list (filters, bulk enable/disable, per-row config links).
 */
export function AppGatewaysContent({ appId }: { appId: string }) {
  const pathKeyState = useGatewayPathKey(appId);

  return (
    <AppDetailFrame
      appId={appId}
      headerAction={<GatewayApiKeyCopy pathKeyState={pathKeyState} />}
    >
      {(app) => (
        <div className="flex min-h-0 flex-1 flex-col">
          <AppNetworksPanel appId={app.id} pathKeyState={pathKeyState} />
        </div>
      )}
    </AppDetailFrame>
  );
}
