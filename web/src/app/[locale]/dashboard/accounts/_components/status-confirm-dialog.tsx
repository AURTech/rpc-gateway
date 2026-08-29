"use client";

import { useTranslations } from "next-intl";
import { toast } from "sonner";

import type { AccountBase } from "@/api/accounts/client";
import { isApiError } from "@/api/client";
import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { useUpdateAccountStatusMutation } from "@/hooks/use-accounts";

const TOAST_KEY = {
  enable: "toast.enabled",
  disable: "toast.disabled",
  revoke: "toast.revoked",
} as const;

/**
 * Enable / disable confirmation. `activate` picks the target status: `active`
 * (enable) vs `disabled` (suspend, treated as destructive). Disabling revokes
 * the account's sessions server-side; disabling an account that has never
 * signed in is phrased as revoking its pending invite.
 */
export function StatusConfirmDialog({
  account,
  activate,
  open,
  onOpenChange,
}: {
  account: AccountBase;
  activate: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("dashboard.admin.accounts");
  const mutation = useUpdateAccountStatusMutation();

  const handleOpenChange = (next: boolean) => {
    if (mutation.isPending) return;
    onOpenChange(next);
  };

  // An account that never signed in is still an open invite, so disabling it
  // is presented as revoking that invite.
  const key = activate ? "enable" : account.activated ? "disable" : "revoke";

  const handleConfirm = () => {
    mutation.mutate(
      { id: account.id, input: { status: activate ? "active" : "disabled" } },
      {
        onSuccess: () => {
          toast.success(t(TOAST_KEY[key]));
          onOpenChange(false);
        },
        onError: (err) => {
          const fallback = t("toast.statusError");
          const msg = isApiError(err) && err.message ? err.message : fallback;
          toast.error(msg);
        },
      },
    );
  };

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={handleOpenChange}
      title={t(`dialog.${key}.title`)}
      description={t(`dialog.${key}.body`, { email: account.email })}
      onConfirm={handleConfirm}
      confirmLabel={t(`dialog.${key}.confirm`)}
      confirmingLabel={t("dialog.saving")}
      cancelLabel={t("dialog.cancel")}
      confirming={mutation.isPending}
      destructive={!activate}
      contentClassName="sm:max-w-dialog"
    />
  );
}
