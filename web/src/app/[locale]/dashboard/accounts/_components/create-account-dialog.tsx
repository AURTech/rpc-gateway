"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { isApiError } from "@/api/client";
import { FormDialog } from "@/components/patterns/form-dialog";
import { Field } from "@/components/patterns/form-field";
import { Input } from "@/components/ui/input";
import { useCreateAccountMutation } from "@/hooks/use-accounts";

const EMAIL_MAX = 320;
// Mirror the backend's loose shape check (server normalizes + validates fully).
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function CreateAccountDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("dashboard.admin.accounts");
  const [email, setEmail] = useState("");
  const mutation = useCreateAccountMutation();

  const reset = () => setEmail("");

  const trimmed = email.trim();
  const canSubmit =
    trimmed.length > 0 && trimmed.length <= EMAIL_MAX && EMAIL_RE.test(trimmed);

  const handleOpenChange = (next: boolean) => {
    if (mutation.isPending) return;
    if (!next) reset();
    onOpenChange(next);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit || mutation.isPending) return;
    mutation.mutate(
      { email: trimmed },
      {
        onSuccess: (account) => {
          toast.success(t("toast.created", { email: account.email }));
          reset();
          onOpenChange(false);
        },
        onError: (err) => {
          const fallback = t("toast.createError");
          const msg = isApiError(err) && err.message ? err.message : fallback;
          toast.error(msg);
        },
      },
    );
  };

  return (
    <FormDialog
      open={open}
      onOpenChange={handleOpenChange}
      title={t("dialog.create.title")}
      description={t("dialog.create.subtitle")}
      onSubmit={handleSubmit}
      submitLabel={t("dialog.create.submit")}
      submittingLabel={t("dialog.creating")}
      cancelLabel={t("dialog.cancel")}
      submitting={mutation.isPending}
      canSubmit={canSubmit}
      contentClassName="sm:max-w-dialog"
    >
      <Field
        label={t("form.email")}
        htmlFor="account-email"
        hint={t("form.emailHint")}
      >
        <Input
          id="account-email"
          type="email"
          autoComplete="off"
          maxLength={EMAIL_MAX}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={t("form.emailPlaceholder")}
          disabled={mutation.isPending}
        />
      </Field>
    </FormDialog>
  );
}
