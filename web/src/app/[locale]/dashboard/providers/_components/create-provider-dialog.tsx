"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { isApiError } from "@/api/client";
import {
  type CreateProviderInput,
  createProvider,
  type RpcProvider,
} from "@/api/providers/client";
import { FormDialog } from "@/components/patterns/form-dialog";

import {
  INITIAL_PROVIDER_FORM,
  PROVIDER_NAME_MAX,
  ProviderFormFields,
  type ProviderFormValues,
} from "./provider-form-fields";

export function CreateProviderDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Lets callers act on the fresh provider, e.g. select it in a picker. */
  onCreated?: (provider: RpcProvider) => void;
}) {
  const t = useTranslations("dashboard.providers");
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ProviderFormValues>(INITIAL_PROVIDER_FORM);

  const mutation = useMutation({
    mutationFn: (input: CreateProviderInput) => createProvider(input),
    meta: { skipGlobalErrorToast: true },
    onSuccess: (provider) => {
      toast.success(t("toast.created", { name: provider.name }));
      queryClient.invalidateQueries({ queryKey: ["providers"] });
      setForm(INITIAL_PROVIDER_FORM);
      onCreated?.(provider);
      onOpenChange(false);
    },
    onError: (err) => {
      const fallback = t("toast.createError");
      const msg = isApiError(err) && err.message ? err.message : fallback;
      toast.error(msg);
    },
  });

  const set = <K extends keyof ProviderFormValues>(
    key: K,
    value: ProviderFormValues[K],
  ) => setForm((prev) => ({ ...prev, [key]: value }));

  const trimmedName = form.name.trim();
  const canSubmit =
    trimmedName.length > 0 &&
    trimmedName.length <= PROVIDER_NAME_MAX &&
    form.secret.trim().length > 0;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit || mutation.isPending) return;
    const hasNetworks = form.networks.length > 0;
    const input: CreateProviderInput = {
      name: trimmedName,
      vendor: form.vendor,
      enabled: true,
      sync_enabled: form.syncEnabled,
      credential: { secret: form.secret },
      only_networks:
        form.netMode === "only" && hasNetworks ? form.networks : undefined,
      ignore_networks:
        form.netMode === "ignore" && hasNetworks ? form.networks : undefined,
    };
    mutation.mutate(input);
  };

  const handleOpenChange = (next: boolean) => {
    if (mutation.isPending) return;
    if (!next) setForm(INITIAL_PROVIDER_FORM);
    onOpenChange(next);
  };

  const busy = mutation.isPending;

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
      submitting={busy}
      canSubmit={canSubmit}
      contentClassName="sm:max-w-dialog"
    >
      <ProviderFormFields
        values={form}
        onChange={set}
        busy={busy}
        idPrefix="prov-create"
        showEnabled={false}
      />
    </FormDialog>
  );
}
