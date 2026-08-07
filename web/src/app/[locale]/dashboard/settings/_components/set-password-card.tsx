"use client";

import { useMutation } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { setPassword } from "@/api/auth/client";
import { isApiError } from "@/api/client";
import { Field } from "@/components/patterns/form-field";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const MIN_LENGTH = 8;
const MAX_LENGTH = 128;

export function SetPasswordCard() {
  const t = useTranslations("dashboard.settings.password");
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const mutation = useMutation({
    mutationFn: setPassword,
    meta: { skipGlobalErrorToast: true },
    onSuccess: () => {
      toast.success(t("success"));
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
    },
    onError: (err) => {
      if (isApiError(err) && err.status === 403) {
        toast.error(t("error_old"));
        return;
      }
      toast.error(t("error"));
    },
  });

  const tooShort = newPassword.length > 0 && newPassword.length < MIN_LENGTH;
  const mismatch =
    confirmPassword.length > 0 && newPassword !== confirmPassword;
  const canSubmit =
    newPassword.length >= MIN_LENGTH &&
    newPassword === confirmPassword &&
    !mutation.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    mutation.mutate({
      new_password: newPassword,
      old_password: oldPassword || undefined,
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">{t("title")}</CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <Field label={t("old_label")} htmlFor="old-password">
            <Input
              id="old-password"
              type="password"
              autoComplete="current-password"
              maxLength={MAX_LENGTH}
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
              placeholder={t("old_placeholder")}
              disabled={mutation.isPending}
            />
          </Field>
          <Field
            label={t("new_label")}
            htmlFor="new-password"
            error={tooShort ? t("too_short") : undefined}
          >
            <Input
              id="new-password"
              type="password"
              autoComplete="new-password"
              maxLength={MAX_LENGTH}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder={t("new_placeholder")}
              disabled={mutation.isPending}
            />
          </Field>
          <Field
            label={t("confirm_label")}
            htmlFor="confirm-password"
            error={mismatch ? t("mismatch") : undefined}
          >
            <Input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              maxLength={MAX_LENGTH}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder={t("confirm_placeholder")}
              disabled={mutation.isPending}
            />
          </Field>
          <div>
            <Button type="submit" disabled={!canSubmit}>
              {mutation.isPending ? t("saving") : t("submit")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
