"use client";

import { Trash2Icon } from "lucide-react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import { isApiError } from "@/api/client";
import type {
  BulkDeleteEndpointResult,
  Endpoint,
} from "@/api/endpoints/client";
import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { useBulkDeleteEndpointsMutation } from "@/hooks/use-endpoints";

export function BulkDeleteEndpointsDialog({
  endpoints,
  open,
  onOpenChange,
  onCompleted,
}: {
  endpoints: readonly Endpoint[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCompleted: (result: BulkDeleteEndpointResult) => void;
}) {
  const t = useTranslations("dashboard.endpoints");
  const mutation = useBulkDeleteEndpointsMutation();

  const remove = () => {
    if (endpoints.length === 0) return;
    mutation.mutate(
      endpoints.map((endpoint) => endpoint.id),
      {
        onSuccess: (result) => {
          const deletedCount = result.deleted.length;
          const referencedCount = result.referenced_ids.length;
          if (referencedCount === 0) {
            toast.success(t("bulk.toast.deleted", { count: deletedCount }));
          } else if (deletedCount === 0) {
            toast.warning(
              t("bulk.toast.allReferenced", { count: referencedCount }),
            );
          } else {
            toast.warning(
              t("bulk.toast.partial", {
                deleted: deletedCount,
                referenced: referencedCount,
              }),
            );
          }
          onCompleted(result);
          onOpenChange(false);
        },
        onError: (error) =>
          toast.error(
            isApiError(error) ? error.message : t("bulk.toast.deleteError"),
          ),
      },
    );
  };

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("bulk.dialog.title")}
      description={t("bulk.dialog.description", { count: endpoints.length })}
      icon={<Trash2Icon />}
      onConfirm={remove}
      confirmLabel={t("bulk.dialog.confirm")}
      confirmingLabel={t("bulk.dialog.deleting")}
      cancelLabel={t("cancel")}
      confirming={mutation.isPending}
    >
      <p className="rounded-lg bg-warning-soft p-3 text-sm text-warning">
        {t("bulk.dialog.referenceWarning")}
      </p>
    </ConfirmDialog>
  );
}
