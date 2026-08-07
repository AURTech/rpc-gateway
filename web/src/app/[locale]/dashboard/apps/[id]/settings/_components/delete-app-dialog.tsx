"use client";

import { useTranslations } from "next-intl";
import { toast } from "sonner";

import type { RpcAppDetail } from "@/api/apps/client";
import { isApiError } from "@/api/client";
import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { useDeleteAppMutation } from "@/hooks/use-apps";
import { useRouter } from "@/i18n/navigation";

export function DeleteAppDialog({
  app,
  open,
  onOpenChange,
}: {
  app: RpcAppDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("dashboard.apps");
  const router = useRouter();
  const mutation = useDeleteAppMutation();

  const handleDelete = () => {
    mutation.mutate(app.id, {
      onSuccess: (result) => {
        if (!result.deleted || result.id !== app.id) {
          toast.error(t("toast.deleteError"));
          return;
        }
        toast.success(t("toast.deleted", { name: app.name }));
        // The app no longer exists, so leave its scoped pages for the list.
        router.push("/dashboard/apps");
      },
      onError: (err) => {
        const fallback = t("toast.deleteError");
        const msg = isApiError(err) && err.message ? err.message : fallback;
        toast.error(msg);
      },
    });
  };

  // Block close while DELETE is in flight; ConfirmDialog guards this internally
  // via `confirming` as well.
  const handleOpenChange = (next: boolean) => {
    if (mutation.isPending) return;
    onOpenChange(next);
  };

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={handleOpenChange}
      title={t("dialog.delete.title")}
      description={t("dialog.delete.body", { name: app.name })}
      onConfirm={handleDelete}
      confirmLabel={t("dialog.delete.confirm")}
      confirmingLabel={t("dialog.saving")}
      cancelLabel={t("dialog.cancel")}
      confirming={mutation.isPending}
      contentClassName="sm:max-w-dialog"
    />
  );
}
