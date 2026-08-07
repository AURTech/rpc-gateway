"use client";

import { useTranslations } from "next-intl";
import { toast } from "sonner";

import type { AccountBase } from "@/api/accounts/client";
import { isApiError } from "@/api/client";
import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { useArchiveAccountMutation } from "@/hooks/use-accounts";

/**
 * Archive (soft-delete) confirmation. Irreversible from the UI: the backend
 * frees the email, revokes sessions, and drops the account out of the list.
 */
export function ArchiveConfirmDialog({
  account,
  open,
  onOpenChange,
}: {
  account: AccountBase;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("dashboard.admin.accounts");
  const mutation = useArchiveAccountMutation();

  const handleOpenChange = (next: boolean) => {
    if (mutation.isPending) return;
    onOpenChange(next);
  };

  const handleConfirm = () => {
    mutation.mutate(account.id, {
      onSuccess: () => {
        toast.success(t("toast.archived", { email: account.email }));
        onOpenChange(false);
      },
      onError: (err) => {
        const fallback = t("toast.archiveError");
        const msg = isApiError(err) && err.message ? err.message : fallback;
        toast.error(msg);
      },
    });
  };

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={handleOpenChange}
      title={t("dialog.archive.title")}
      description={t("dialog.archive.body", { email: account.email })}
      onConfirm={handleConfirm}
      confirmLabel={t("dialog.archive.confirm")}
      confirmingLabel={t("dialog.saving")}
      cancelLabel={t("dialog.cancel")}
      confirming={mutation.isPending}
      destructive
      contentClassName="sm:max-w-dialog"
    />
  );
}
