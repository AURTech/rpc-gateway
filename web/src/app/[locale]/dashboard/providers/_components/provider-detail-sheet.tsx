"use client";

import { useTranslations } from "next-intl";
import { type FormEvent, useRef, useState } from "react";
import { toast } from "sonner";

import { isApiError } from "@/api/client";
import type {
  RpcProvider,
  RpcProviderNetworkPair,
  UpdateProviderInput,
} from "@/api/providers/client";
import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { DetailDrawer } from "@/components/patterns/detail-drawer";
import { Button } from "@/components/ui/button";
import {
  useProviderQuery,
  useUpdateProviderMutation,
} from "@/hooks/use-providers";

import { DeleteProviderDialog } from "./delete-provider-dialog";
import type { NetworkFilterMode } from "./network-filter-field";
import {
  PROVIDER_NAME_MAX,
  ProviderFormFields,
  type ProviderFormValues,
} from "./provider-form-fields";

const FORM_ID = "provider-edit-form";

type ProviderUpdateFields = Omit<UpdateProviderInput, "expected_version">;
type PendingConfirm = "disable" | "secret" | "disableAndSecret" | null;

type NetworkDraft = {
  mode: NetworkFilterMode;
  networks: RpcProviderNetworkPair[];
};

function readNetworkDraft(provider: RpcProvider): NetworkDraft {
  if (provider.only_networks.length > 0) {
    return { mode: "only", networks: provider.only_networks };
  }
  if (provider.ignore_networks.length > 0) {
    return { mode: "ignore", networks: provider.ignore_networks };
  }
  return { mode: "none", networks: [] };
}

function readProviderForm(provider: RpcProvider): ProviderFormValues {
  const network = readNetworkDraft(provider);
  return {
    name: provider.name,
    vendor: provider.vendor,
    secret: provider.credential.secret,
    syncEnabled: provider.sync_enabled,
    enabled: provider.enabled,
    netMode: network.mode,
    networks: network.networks,
  };
}

function sameNetworkPairs(
  left: RpcProviderNetworkPair[],
  right: RpcProviderNetworkPair[],
) {
  if (left.length !== right.length) return false;
  return left.every(
    (pair, index) =>
      pair.chain === right[index]?.chain &&
      pair.network === right[index]?.network,
  );
}

function networkInput(
  mode: NetworkFilterMode,
  networks: RpcProviderNetworkPair[],
): Pick<ProviderUpdateFields, "only_networks" | "ignore_networks"> {
  return {
    only_networks: mode === "only" ? networks : [],
    ignore_networks: mode === "ignore" ? networks : [],
  };
}

function buildProviderUpdate(
  provider: RpcProvider,
  form: ProviderFormValues,
): ProviderUpdateFields {
  const input: ProviderUpdateFields = {};
  const name = form.name.trim();
  const secret = form.secret.trim();

  if (name !== provider.name) input.name = name;
  if (secret !== provider.credential.secret) {
    input.credential = { secret };
  }
  if (form.syncEnabled !== provider.sync_enabled) {
    input.sync_enabled = form.syncEnabled;
  }
  if (form.enabled !== provider.enabled) input.enabled = form.enabled;

  const networks = networkInput(form.netMode, form.networks);
  if (
    !sameNetworkPairs(networks.only_networks ?? [], provider.only_networks) ||
    !sameNetworkPairs(networks.ignore_networks ?? [], provider.ignore_networks)
  ) {
    Object.assign(input, networks);
  }

  return input;
}

function ProviderEditSheet({
  provider,
  open,
  onOpenChange,
}: {
  provider: RpcProvider;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("dashboard.providers");
  const update = useUpdateProviderMutation();
  const busy = update.isPending;
  const [form, setForm] = useState<ProviderFormValues>(() =>
    readProviderForm(provider),
  );
  const [confirm, setConfirm] = useState<PendingConfirm>(null);
  const [pendingInput, setPendingInput] = useState<ProviderUpdateFields | null>(
    null,
  );
  const [deleteOpen, setDeleteOpen] = useState(false);

  const set = <K extends keyof ProviderFormValues>(
    key: K,
    value: ProviderFormValues[K],
  ) => setForm((previous) => ({ ...previous, [key]: value }));

  const input = buildProviderUpdate(provider, form);
  const dirty = Object.keys(input).length > 0;
  const validName =
    form.name.trim().length > 0 && form.name.trim().length <= PROVIDER_NAME_MAX;
  const validSecret = form.secret.trim().length > 0;
  const canSubmit = dirty && validName && validSecret;

  const handleOpenChange = (next: boolean) => {
    if (busy) return;
    onOpenChange(next);
  };

  const saveProvider = (changes: ProviderUpdateFields) => {
    if (busy) return;
    update.mutate(
      {
        id: provider.id,
        input: { ...changes, expected_version: provider.version },
      },
      {
        onSuccess: () => {
          toast.success(t("toast.updated"));
          setConfirm(null);
          setPendingInput(null);
          onOpenChange(false);
        },
        onError: (error) => {
          const fallback = t("toast.updateError");
          toast.error(
            isApiError(error) && error.message ? error.message : fallback,
          );
        },
      },
    );
  };

  const requestSave = () => {
    if (!canSubmit || busy) return;
    const replacesSecret = input.credential !== undefined;
    const disablesProvider = input.enabled === false;

    if (replacesSecret || disablesProvider) {
      setPendingInput(input);
      setConfirm(
        replacesSecret && disablesProvider
          ? "disableAndSecret"
          : replacesSecret
            ? "secret"
            : "disable",
      );
      return;
    }

    saveProvider(input);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    requestSave();
  };

  const confirmTitle =
    confirm === "disableAndSecret"
      ? t("detail.sensitiveChangesTitle")
      : confirm === "secret"
        ? t("detail.secretReplaceTitle")
        : t("detail.disableTitle");
  const confirmDescription =
    confirm === "disableAndSecret"
      ? t("detail.sensitiveChangesBody", { name: provider.name })
      : confirm === "secret"
        ? t("detail.secretReplaceBody")
        : t("detail.disableBody", { name: provider.name });
  const confirmLabel =
    confirm === "disableAndSecret"
      ? t("dialog.edit.submit")
      : confirm === "secret"
        ? t("detail.secretReplaceConfirm")
        : t("actions.toggleOff");

  return (
    <DetailDrawer
      open={open}
      onOpenChange={handleOpenChange}
      title={t("dialog.edit.title")}
      description={t("dialog.edit.subtitle")}
      closeLabel={t("actions.hideDetails")}
      footer={
        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={() => handleOpenChange(false)}
            disabled={busy}
          >
            {t("dialog.cancel")}
          </Button>
          <Button type="submit" form={FORM_ID} disabled={!canSubmit || busy}>
            {busy ? t("dialog.saving") : t("dialog.edit.submit")}
          </Button>
        </div>
      }
    >
      <form
        id={FORM_ID}
        className="flex flex-col gap-4"
        noValidate
        onSubmit={handleSubmit}
      >
        <ProviderFormFields
          values={form}
          onChange={set}
          busy={busy}
          vendorLocked
          secretHint={t("form.secretKeepHint")}
          idPrefix="prov-edit"
        />

        <section className="mt-2 flex flex-col gap-3 border-t border-ink-wash pt-6">
          <div>
            <h3 className="text-md font-semibold text-ink-900">
              {t("detail.deleteTitle")}
            </h3>
            <p className="mt-1 text-sm text-ink-500">
              {t("detail.dangerBody")}
            </p>
          </div>
          <Button
            type="button"
            variant="destructive"
            className="self-start"
            onClick={() => setDeleteOpen(true)}
            disabled={busy}
          >
            {t("actions.deleteProvider")}
          </Button>
        </section>
      </form>

      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(next) => {
          if (!next && !busy) {
            setConfirm(null);
            setPendingInput(null);
          }
        }}
        title={confirmTitle}
        description={confirmDescription}
        onConfirm={() => pendingInput && saveProvider(pendingInput)}
        confirmLabel={confirmLabel}
        cancelLabel={t("dialog.cancel")}
        confirming={busy}
        confirmingLabel={t("dialog.saving")}
      />

      <DeleteProviderDialog
        provider={provider}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        onDeleted={() => onOpenChange(false)}
      />
    </DetailDrawer>
  );
}

/** Standard edit form in the shared responsive Sheet/Drawer container. */
export function ProviderDetailSheet({
  providerId,
  open,
  onOpenChange,
}: {
  providerId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("dashboard.providers");
  const query = useProviderQuery(open ? providerId : null);

  // Keep the last loaded record painted through the close animation so the
  // drawer never blanks out as it slides away.
  const shownRef = useRef<{ id: string; provider: RpcProvider } | null>(null);
  if (query.data && providerId) {
    shownRef.current = { id: providerId, provider: query.data };
  }
  const shownProvider =
    providerId && shownRef.current?.id === providerId
      ? shownRef.current.provider
      : null;
  const provider = query.data ?? (open ? shownProvider : null);

  if (provider) {
    return (
      <ProviderEditSheet
        key={`${provider.id}:${provider.version}`}
        provider={provider}
        open={open}
        onOpenChange={onOpenChange}
      />
    );
  }

  return (
    <DetailDrawer
      open={open && query.isError}
      onOpenChange={onOpenChange}
      title={t("dialog.edit.title")}
      description={t("dialog.edit.subtitle")}
      closeLabel={t("actions.hideDetails")}
    >
      {query.isError ? (
        <div role="alert" className="flex flex-col items-center gap-2 py-10">
          <p className="text-md font-semibold text-ink-900">
            {t("detail.notFoundTitle")}
          </p>
          <p className="text-sm text-ink-500">{t("detail.notFoundBody")}</p>
        </div>
      ) : (
        <p className="py-8 text-center text-sm text-ink-500">
          {t("detail.loading")}
        </p>
      )}
    </DetailDrawer>
  );
}
