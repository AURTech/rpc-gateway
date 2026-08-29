"use client";

import { useTranslations } from "next-intl";
import { toast } from "sonner";

import { isApiError } from "@/api/client";
import type { Endpoint } from "@/api/endpoints/client";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  useDeleteEndpointMutation,
  useEndpointRouteBindingsQuery,
} from "@/hooks/use-endpoints";

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
  const bindingsQuery = useEndpointRouteBindingsQuery(endpoint?.id ?? null);
  const providerManaged = endpoint?.origin_type === "provider";
  const bindingCount = bindingsQuery.data?.total ?? 0;
  const busy = mutation.isPending || bindingsQuery.isLoading;
  const confirmDisabled = providerManaged || busy || bindingsQuery.isError;

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
        </DialogHeader>
        {providerManaged ? (
          <p className="rounded-lg bg-warning-soft p-3 text-sm text-warning">
            {t("delete.providerManaged")}
          </p>
        ) : null}
        {bindingCount > 0 || bindingsQuery.isError ? (
          <div className="rounded-lg bg-danger-soft p-3 text-sm text-danger">
            <p className="font-semibold">
              {bindingCount > 0
                ? t("delete.bindingWarningTitle", { count: bindingCount })
                : t("delete.bindingWarningFallbackTitle")}
            </p>
            <p className="mt-1 text-danger/80">
              {t("delete.bindingWarningBody")}
            </p>
            {bindingsQuery.isError ? (
              <Button
                className="mt-3"
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => bindingsQuery.refetch()}
              >
                {t("retry")}
              </Button>
            ) : null}
          </div>
        ) : null}
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={() => onOpenChange(false)}
          >
            {t("cancel")}
          </Button>
          <Button
            type="button"
            variant="destructive"
            disabled={confirmDisabled}
            onClick={remove}
          >
            {t("actions.delete")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
