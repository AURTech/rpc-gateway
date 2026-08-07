import type { RpcProviderSyncStatus } from "@/api/providers/client";
import { Badge } from "@/components/ui/badge";

const SYNC_STATUS_VARIANTS: Record<
  RpcProviderSyncStatus,
  React.ComponentProps<typeof Badge>["variant"]
> = {
  never: "neutral",
  success: "positive",
  partial: "warning",
  failed: "danger",
};

/** Provider-level last-sync outcome badge (never / success / partial / failed),
 *  shared by the desktop row and the mobile card. */
export function SyncStatusPill({
  status,
  label,
}: {
  status: RpcProviderSyncStatus;
  label: string;
}) {
  return (
    <Badge variant={SYNC_STATUS_VARIANTS[status]} dot>
      {label}
    </Badge>
  );
}
