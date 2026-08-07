"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { isApiError } from "@/api/client";
import { deleteProvider, type RpcProviderBase } from "@/api/providers/client";
import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { endpointsKeys } from "@/hooks/use-endpoints";
import { providersKeys } from "@/hooks/use-providers";

export function DeleteProviderDialog({
  provider,
  open,
  onOpenChange,
  onDeleted,
}: {
  provider: RpcProviderBase;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called after a successful delete — e.g. to redirect off the detail page. */
  onDeleted?: () => void;
}) {
  const t = useTranslations("dashboard.providers");
  const queryClient = useQueryClient();
  const [deleteUnreferencedEndpoints, setDeleteUnreferencedEndpoints] =
    useState(false);

  const mutation = useMutation({
    mutationFn: () =>
      deleteProvider(provider.id, {
        delete_unreferenced_endpoints: deleteUnreferencedEndpoints,
      }),
    meta: { skipGlobalErrorToast: true },
    onSuccess: () => {
      toast.success(t("toast.deleted", { name: provider.name }));
      queryClient.invalidateQueries({ queryKey: providersKeys.lists() });
      queryClient.invalidateQueries({ queryKey: endpointsKeys.lists() });
      queryClient.removeQueries({
        queryKey: providersKeys.detail(provider.id),
      });
      queryClient.removeQueries({
        queryKey: providersKeys.endpoints(provider.id),
      });
      setDeleteUnreferencedEndpoints(false);
      onOpenChange(false);
      onDeleted?.();
    },
    onError: (err) => {
      const fallback = t("toast.deleteError");
      const msg = isApiError(err) && err.message ? err.message : fallback;
      toast.error(msg);
    },
  });

  const handleOpenChange = (next: boolean) => {
    if (!next) setDeleteUnreferencedEndpoints(false);
    onOpenChange(next);
  };

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={handleOpenChange}
      title={t("dialog.delete.title")}
      description={t("dialog.delete.body", { name: provider.name })}
      onConfirm={() => mutation.mutate()}
      confirmLabel={t("dialog.delete.confirm")}
      confirmingLabel={t("dialog.saving")}
      cancelLabel={t("dialog.cancel")}
      confirming={mutation.isPending}
      contentClassName="sm:max-w-dialog"
    >
      <div className="flex items-start gap-3 rounded-lg border border-ink-100 p-4">
        <Checkbox
          id="delete-provider-endpoints"
          checked={deleteUnreferencedEndpoints}
          onCheckedChange={(checked) =>
            setDeleteUnreferencedEndpoints(checked === true)
          }
          disabled={mutation.isPending}
          aria-describedby="delete-provider-endpoints-hint"
        />
        <div className="grid gap-1">
          <label
            htmlFor="delete-provider-endpoints"
            className="text-sm font-medium text-ink-900"
          >
            {t("dialog.delete.deleteEndpoints")}
          </label>
          <p
            id="delete-provider-endpoints-hint"
            className="text-xs text-ink-500"
          >
            {t("dialog.delete.deleteEndpointsHint")}
          </p>
        </div>
      </div>
    </ConfirmDialog>
  );
}
