"use client";

import { AppDetailFrame } from "./app-detail-frame";
import { AppUsagePanel } from "./app-usage-panel";

/** App-scoped usage page: shared app header followed by call-level charts. */
export function AppUsageContent({ appId }: { appId: string }) {
  return (
    <AppDetailFrame appId={appId} showHeader={false}>
      {(app) => <AppUsagePanel appId={app.id} />}
    </AppDetailFrame>
  );
}
