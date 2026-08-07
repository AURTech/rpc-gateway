"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { isApiError } from "@/api/client";
import type {
  RpcProviderBase,
  RpcProviderSyncResult,
} from "@/api/providers/client";
import { useSyncProviderMutation } from "@/hooks/use-providers";

import { SyncResultDialog } from "./sync-result-dialog";

/**
 * Sync wiring shared by the row, the card and the detail drawer. Fires the
 * blocking `POST /sync`, announces the start with a toast (the trigger closes
 * its menu right away, so this is the only start-of-work signal), and surfaces
 * the outcome in the result dialog. Callers read `syncPending` to paint their
 * own in-progress affordance (row cell / card meta / detail button).
 */
export function useProviderSync(provider: RpcProviderBase) {
  const t = useTranslations("dashboard.providers");
  const [syncResult, setSyncResult] = useState<RpcProviderSyncResult | null>(
    null,
  );
  const syncMutation = useSyncProviderMutation();

  const runSync = () => {
    toast(t("toast.syncStarted", { name: provider.name }));
    syncMutation.mutate(provider.id, {
      onSuccess: (result) => setSyncResult(result),
      onError: (err) => {
        const fallback = t("toast.syncError");
        toast.error(isApiError(err) && err.message ? err.message : fallback);
      },
    });
  };

  const syncResultDialog = (
    <SyncResultDialog
      providerName={provider.name}
      result={syncResult}
      open={syncResult !== null}
      onOpenChange={(next) => {
        if (!next) setSyncResult(null);
      }}
    />
  );

  return { runSync, syncPending: syncMutation.isPending, syncResultDialog };
}
