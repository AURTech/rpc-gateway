"use client";

import { useTranslations } from "next-intl";
import { toast } from "sonner";

import { isApiError } from "@/api/client";
import type { Endpoint } from "@/api/endpoints/client";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useDeleteEndpointMutation } from "@/hooks/use-endpoints";

export function DeleteEndpointDialog({
  endpoint,
  open,
  onOpenChange,
  onDeleted,
}: {
  endpoint: Endpoint | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted?: (id: string) => void;
}) {
  const t = useTranslations("dashboard.endpoints");
  const mutation = useDeleteEndpointMutation();
  const providerManaged = endpoint?.origin_type === "provider";

  const remove = () => {
    if (!endpoint) return;
    mutation.mutate(endpoint.id, {
      onSuccess: () => {
        toast.success(t("toast.deleted"));
        onDeleted?.(endpoint.id);
        onOpenChange(false);
      },
      onError: (error) =>
        toast.error(isApiError(error) ? error.message : t("toast.deleteError")),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("delete.title")}</DialogTitle>
          <DialogDescription>
            {t("delete.description", { name: endpoint?.name ?? "" })}
          </DialogDescription>
        </DialogHeader>
        {providerManaged ? (
          <p className="rounded-lg bg-warning-soft p-3 text-sm text-warning">
            {t("delete.providerWarning")}
          </p>
        ) : null}
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            disabled={mutation.isPending}
            onClick={() => onOpenChange(false)}
          >
            {t("cancel")}
          </Button>
          <Button
            type="button"
            variant="destructive"
            disabled={mutation.isPending}
            onClick={remove}
          >
            {t("actions.delete")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
