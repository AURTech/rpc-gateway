"use client";

import { AlertTriangleIcon, LoaderCircleIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { providerNetworksForVendor } from "@/api/providers/capabilities";
import type {
  RpcProvider,
  RpcProviderNetworkPair,
} from "@/api/providers/client";
import { ChainNetworkMultiSelect } from "@/components/patterns/chain-network-select";
import { Field } from "@/components/patterns/form-field";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useUpdateProvider } from "./use-providers";

function SettingsForm({ provider }: { provider: RpcProvider }) {
  const t = useTranslations("dashboard.endpointProviders.settings");
  const update = useUpdateProvider(provider.id);
  const [name, setName] = useState(provider.name);
  const [enabled, setEnabled] = useState(provider.enabled);
  const [syncEnabled, setSyncEnabled] = useState(provider.sync_enabled);
  // Empty means "every supported network"; the API stores that as `null`.
  const [networks, setNetworks] = useState<RpcProviderNetworkPair[]>(
    provider.networks ? [...provider.networks] : [],
  );
  const [replaceApiKey, setReplaceApiKey] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const hasApiKey = provider.credential.has_secret;

  async function save() {
    try {
      await update.mutateAsync({
        expected_version: provider.version,
        name: name.trim(),
        enabled,
        sync_enabled: syncEnabled,
        networks: networks.length > 0 ? networks : null,
        ...(replaceApiKey && apiKey ? { credential: { secret: apiKey } } : {}),
      });
      setApiKey("");
      setReplaceApiKey(false);
      toast.success(t("saved"));
    } catch {
      toast.error(t("saveError"));
    }
  }

  function cancelApiKeyChange() {
    setApiKey("");
    setReplaceApiKey(false);
  }

  return (
    <div className="space-y-7">
      <div className="max-w-xl">
        <Field label={t("name.title")} htmlFor="settings-name" required>
          <Input
            id="settings-name"
            value={name}
            maxLength={128}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
      </div>

      {!replaceApiKey ? (
        <div className="flex items-start justify-between gap-6">
          <div>
            <p className="text-sm font-semibold text-ink-900">
              {t("credential.title")}
            </p>
            <p className="mt-1 text-sm text-ink-500">
              {t("credential.description")}
            </p>
          </div>
          <Button variant="soft" onClick={() => setReplaceApiKey(true)}>
            {t(hasApiKey ? "credential.replace" : "credential.add")}
          </Button>
        </div>
      ) : (
        <div className="max-w-xl space-y-3">
          <Field
            label={t(
              hasApiKey ? "credential.newCredential" : "credential.title",
            )}
            htmlFor="settings-api-key"
            hint={hasApiKey ? undefined : t("credential.addHint")}
            required
          >
            <div className="flex items-center gap-2">
              <Input
                id="settings-api-key"
                className="min-w-0 flex-1"
                type="password"
                autoComplete="new-password"
                maxLength={4096}
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
              />
              <Button
                type="button"
                variant="outline"
                onClick={cancelApiKeyChange}
              >
                {t("credential.cancel")}
              </Button>
            </div>
          </Field>
          {hasApiKey ? (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-lg bg-warning-soft px-3 py-2.5 text-warning"
            >
              <AlertTriangleIcon
                className="mt-0.5 size-4 shrink-0"
                aria-hidden
              />
              <p className="text-sm">{t("credential.replaceWarning")}</p>
            </div>
          ) : null}
        </div>
      )}

      <div className="space-y-3">
        <p className="text-sm font-semibold text-ink-900">
          {t("networks.title")}
        </p>
        <ChainNetworkMultiSelect
          options={providerNetworksForVendor(provider.vendor)}
          value={networks}
          onChange={setNetworks}
          inputId="settings-network-search"
          disabled={update.isPending}
        />
      </div>

      <div className="divide-y divide-table-frame">
        <div className="flex items-start justify-between gap-6 pb-4">
          <span>
            <span
              id="settings-schedule-label"
              className="block text-sm font-semibold text-ink-900"
            >
              {t("sync.schedule")}
            </span>
            <span className="mt-1 block text-sm text-ink-500">
              {t("sync.scheduleHint")}
            </span>
          </span>
          <Switch
            id="settings-schedule"
            aria-labelledby="settings-schedule-label"
            checked={syncEnabled}
            onCheckedChange={setSyncEnabled}
          />
        </div>
        <div className="flex items-start justify-between gap-6 pt-4">
          <span>
            <span
              id="settings-enabled-label"
              className="block text-sm font-semibold text-ink-900"
            >
              {t("sync.enabled")}
            </span>
            <span className="mt-1 block text-sm text-ink-500">
              {t("sync.enabledHint")}
            </span>
          </span>
          <Switch
            id="settings-enabled"
            aria-labelledby="settings-enabled-label"
            checked={enabled}
            onCheckedChange={setEnabled}
          />
        </div>
      </div>

      {update.isError ? (
        <p role="alert" className="text-sm text-danger">
          {update.error.message}
        </p>
      ) : null}
      <div className="flex justify-end">
        <Button
          disabled={
            update.isPending || !name.trim() || (replaceApiKey && !apiKey)
          }
          onClick={save}
        >
          {update.isPending ? (
            <LoaderCircleIcon className="animate-spin" />
          ) : null}
          {t("save")}
        </Button>
      </div>
    </div>
  );
}

export function ProviderSettingsDialog({
  provider,
  open,
  onOpenChange,
}: {
  provider: RpcProvider | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("dashboard.endpointProviders.settings");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-xl"
        closeLabel={t("close")}
      >
        <DialogHeader>
          <DialogTitle>{t("dialogTitle")}</DialogTitle>
          <DialogDescription>{t("dialogDescription")}</DialogDescription>
        </DialogHeader>
        {provider ? (
          <SettingsForm key={provider.version} provider={provider} />
        ) : (
          <Skeleton className="h-panel w-full rounded-xl" />
        )}
      </DialogContent>
    </Dialog>
  );
}
