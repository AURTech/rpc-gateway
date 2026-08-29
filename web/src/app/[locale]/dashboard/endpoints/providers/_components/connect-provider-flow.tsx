"use client";

import { ArrowLeftIcon, ArrowRightIcon, LoaderCircleIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { providerNetworksForVendor } from "@/api/providers/capabilities";
import {
  RPC_PROVIDER_VENDORS,
  type RpcProviderNetworkPair,
  type RpcProviderVendor,
  syncProvider,
} from "@/api/providers/client";
import { ChainNetworkMultiSelect } from "@/components/patterns/chain-network-select";
import { Field } from "@/components/patterns/form-field";
import { Button } from "@/components/ui/button";
import { DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Stepper } from "@/components/ui/stepper";
import { Switch } from "@/components/ui/switch";
import { ProviderNetworkIconGroup } from "./provider-network-visuals";
import { VendorMark } from "./provider-ui";
import { useCreateProvider, useProviderRun } from "./use-providers";

interface Draft {
  vendor: RpcProviderVendor;
  name: string;
  apiKey: string;
  syncEnabled: boolean;
  /** Empty means every network the vendor supports; the API takes `null`. */
  networks: RpcProviderNetworkPair[];
}

const initialDraft: Draft = {
  vendor: "alchemy",
  name: "",
  apiKey: "",
  syncEnabled: true,
  networks: [],
};

const stepKeys = ["provider", "configure", "review"] as const;

export function ConnectProviderFlow({
  onComplete,
  onFixApiKey,
}: {
  onComplete: (id: string) => void;
  onFixApiKey: (id: string) => void;
}) {
  const t = useTranslations("dashboard.endpointProviders.onboarding");
  const create = useCreateProvider();
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<Draft>(initialDraft);
  const [discoveryError, setDiscoveryError] = useState<string | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [syncStarting, setSyncStarting] = useState(false);
  const handledRun = useRef<string | null>(null);
  const runQuery = useProviderRun(savedId ?? "", runId);

  const run = runQuery.data;
  useEffect(() => {
    if (!savedId || !run || handledRun.current === run.id) return;
    if (run.state === "success" || run.state === "partial") {
      handledRun.current = run.id;
      onComplete(savedId);
      return;
    }
    if (run.state === "failed") {
      handledRun.current = run.id;
      setDiscoveryError(run.error || t("error.credential"));
      setRunId(null);
    }
  }, [onComplete, run, savedId, t]);

  useEffect(() => {
    if (!runId || !runQuery.isError) return;
    setDiscoveryError(runQuery.error.message);
    setRunId(null);
  }, [runId, runQuery.error, runQuery.isError]);

  function chooseVendor(vendor: RpcProviderVendor) {
    const supported = new Set(
      providerNetworksForVendor(vendor).map(
        (pair) => `${pair.chain}:${pair.network}`,
      ),
    );
    setDraft((current) => ({
      ...current,
      vendor,
      networks: current.networks.filter((pair) =>
        supported.has(`${pair.chain}:${pair.network}`),
      ),
    }));
  }

  async function startDiscovery(providerId: string) {
    setDiscoveryError(null);
    setRunId(null);
    setSyncStarting(true);
    try {
      const nextRun = await syncProvider(providerId);
      setRunId(nextRun.id);
    } catch (error) {
      setDiscoveryError(
        error instanceof Error ? error.message : t("error.unknown"),
      );
    } finally {
      setSyncStarting(false);
    }
  }

  async function saveAndDiscover() {
    setDiscoveryError(null);
    try {
      const provider = await create.mutateAsync({
        name: draft.name.trim(),
        vendor: draft.vendor,
        credential: { secret: draft.apiKey },
        enabled: true,
        sync_enabled: draft.syncEnabled,
        // The API rejects an empty list; `null` is how "all networks" is stored.
        networks: draft.networks.length > 0 ? draft.networks : null,
      });
      setSavedId(provider.id);
      await startDiscovery(provider.id);
    } catch {
      // Mutation state owns the save error and keeps the user on Review.
    }
  }

  const canContinue =
    step === 0 || (draft.name.trim().length > 0 && draft.apiKey.length > 0);
  const discovering =
    syncStarting ||
    (runId !== null &&
      (!run || run.state === "queued" || run.state === "running"));
  const busy = create.isPending || discovering;
  const currentStep = stepKeys[step] ?? stepKeys[0];

  return (
    <div className="w-full space-y-7">
      <header className="space-y-1 pr-8">
        <DialogTitle className="text-xl leading-snug">
          {t(`${currentStep}.title`)}
        </DialogTitle>
        <DialogDescription className="text-ink-500">
          {t(`${currentStep}.description`)}
        </DialogDescription>
      </header>

      <Stepper currentStep={step} size="sm">
        {stepKeys.map((item) => (
          <Stepper.Step key={item}>
            <Stepper.Indicator />
            <Stepper.Content>
              <Stepper.Title>{t(`steps.${item}.title`)}</Stepper.Title>
            </Stepper.Content>
            <Stepper.Separator />
          </Stepper.Step>
        ))}
      </Stepper>

      <div className="pt-2">
        {step === 0 ? (
          <section aria-label={t("provider.title")}>
            <div className="grid gap-2">
              {RPC_PROVIDER_VENDORS.map((vendor) => {
                const selected = draft.vendor === vendor;
                return (
                  <button
                    key={vendor}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => chooseVendor(vendor)}
                    className="flex items-center gap-3 rounded-xl bg-ink-wash px-4 py-3 text-left outline-none transition-colors hover:bg-stripe focus-visible:ring-2 focus-visible:ring-brand/40 aria-pressed:bg-brand-soft"
                  >
                    <VendorMark label={t(`vendors.${vendor}`)} />
                    <span>
                      <span className="block font-semibold text-ink-900">
                        {t(`vendors.${vendor}`)}
                      </span>
                      <span className="block text-xs text-ink-500">
                        {t("provider.available")}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </section>
        ) : null}

        {step === 1 ? (
          <section aria-label={t("configure.title")}>
            <div className="space-y-7">
              <div className="space-y-6">
                <Field
                  label={t("configure.name")}
                  htmlFor="provider-name"
                  hint={t("configure.nameHint")}
                  required
                >
                  <Input
                    id="provider-name"
                    value={draft.name}
                    maxLength={128}
                    autoComplete="off"
                    onChange={(event) =>
                      setDraft((current) => ({
                        ...current,
                        name: event.target.value,
                      }))
                    }
                  />
                </Field>
                <Field
                  label={t("configure.credential")}
                  htmlFor="provider-api-key"
                  hint={t("configure.credentialHint", {
                    vendor: t(`vendors.${draft.vendor}`),
                  })}
                  required
                >
                  <Input
                    id="provider-api-key"
                    type="password"
                    value={draft.apiKey}
                    maxLength={4096}
                    autoComplete="new-password"
                    spellCheck={false}
                    onChange={(event) =>
                      setDraft((current) => ({
                        ...current,
                        apiKey: event.target.value,
                      }))
                    }
                  />
                </Field>
                <label
                  htmlFor="provider-daily-sync"
                  className="flex items-start justify-between gap-6"
                >
                  <span>
                    <span className="block text-sm font-semibold text-ink-900">
                      {t("configure.schedule")}
                    </span>
                    <span className="mt-1 block text-sm text-ink-500">
                      {t("configure.scheduleHint")}
                    </span>
                  </span>
                  <Switch
                    id="provider-daily-sync"
                    checked={draft.syncEnabled}
                    onCheckedChange={(syncEnabled) =>
                      setDraft((current) => ({ ...current, syncEnabled }))
                    }
                  />
                </label>
              </div>
              <section aria-labelledby="provider-network-scope-title">
                <h3
                  id="provider-network-scope-title"
                  className="text-sm font-semibold text-ink-900"
                >
                  {t("configure.scope")}
                </h3>
                <div className="mt-3">
                  <ChainNetworkMultiSelect
                    options={providerNetworksForVendor(draft.vendor)}
                    value={draft.networks}
                    onChange={(networks) =>
                      setDraft((current) => ({ ...current, networks }))
                    }
                    inputId="provider-network-search"
                    disabled={busy}
                  />
                </div>
              </section>
            </div>
          </section>
        ) : null}

        {step === 2 ? (
          <section aria-label={t("review.title")}>
            <dl className="grid gap-5 rounded-lg bg-ink-wash p-5">
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-ink-500">
                  {t("review.providerName")}
                </dt>
                <dd className="mt-1 font-semibold text-ink-900">
                  {draft.name}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-ink-500">
                  {t("review.provider")}
                </dt>
                <dd className="mt-1 font-semibold text-ink-900">
                  {t(`vendors.${draft.vendor}`)}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-ink-500">
                  {t("review.scope")}
                </dt>
                <dd className="mt-1 text-ink-900">
                  {draft.networks.length === 0 ? (
                    <ProviderNetworkIconGroup
                      networks={null}
                      vendor={draft.vendor}
                    />
                  ) : (
                    t("review.selectedNetworks", {
                      count: draft.networks.length,
                    })
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-ink-500">
                  {t("review.schedule")}
                </dt>
                <dd className="mt-1 text-ink-900">
                  {t(draft.syncEnabled ? "review.daily" : "review.manual")}
                </dd>
              </div>
            </dl>
            {create.isError ? (
              <p role="alert" className="mt-5 text-sm text-danger">
                {create.error.message}
              </p>
            ) : null}
            {discovering ? (
              <p
                aria-live="polite"
                className="mt-5 flex items-center gap-2 text-sm text-ink-500"
              >
                <LoaderCircleIcon className="size-4 animate-spin" aria-hidden />
                {t("review.discovering")}
              </p>
            ) : null}
            {discoveryError && savedId ? (
              <div role="alert" className="mt-5 rounded-lg bg-warning-soft p-4">
                <p className="font-semibold text-warning">
                  {t("error.discoveryTitle")}
                </p>
                <p className="mt-1 text-sm text-ink-700">{discoveryError}</p>
                <div className="mt-4 flex gap-2">
                  <Button
                    variant="soft"
                    onClick={() => startDiscovery(savedId)}
                  >
                    {t("actions.retry")}
                  </Button>
                  <Button variant="ghost" onClick={() => onFixApiKey(savedId)}>
                    {t("actions.updateCredential")}
                  </Button>
                </div>
              </div>
            ) : null}
          </section>
        ) : null}
      </div>

      <div className="flex justify-between">
        <Button
          variant="ghost"
          disabled={step === 0 || busy || savedId !== null}
          onClick={() => setStep((current) => current - 1)}
        >
          <ArrowLeftIcon />
          {t("actions.back")}
        </Button>
        {step < 2 ? (
          <Button
            disabled={!canContinue}
            onClick={() => setStep((current) => current + 1)}
          >
            {t("actions.continue")}
            <ArrowRightIcon />
          </Button>
        ) : discoveryError ? null : (
          <Button disabled={busy || savedId !== null} onClick={saveAndDiscover}>
            {busy ? <LoaderCircleIcon className="animate-spin" /> : null}
            {t("actions.saveDiscover")}
          </Button>
        )}
      </div>
    </div>
  );
}
