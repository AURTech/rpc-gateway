"use client";

import { useTranslations } from "next-intl";
import { type FormEvent, useRef, useState } from "react";
import { toast } from "sonner";
import { type CreatedRpcApp, setAppProvider } from "@/api/apps/client";
import { isApiError } from "@/api/client";
import { listGateways } from "@/api/gateways/client";
import { syncProvider } from "@/api/providers/client";
import { Field } from "@/components/patterns/form-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Stepper } from "@/components/ui/stepper";
import { Switch } from "@/components/ui/switch";
import { useCreateAppMutation } from "@/hooks/use-apps";
import { useBulkUpdateGatewaysMutation } from "@/hooks/use-gateways";
import { Link } from "@/i18n/navigation";
import { cn } from "@/lib/utils";

import { ALL_NETWORK_KEYS, CHAIN_CATALOG, networkKey } from "./chain-catalog";
import { ChainSelectCard } from "./chain-select-card";
import { RpcAccessStep } from "./rpc-access-step";

// An app owns at most one gateway per (chain, network) pair (~20 across the
// registry); the list API caps `size` at 50, so a single page always covers the
// full catalog snapshot provisioned at create time.
const APP_GATEWAYS_SIZE = 50;

type Step = "details" | "networks" | "rpcAccess";

const STEP_INDEX: Record<Step, number> = {
  details: 0,
  networks: 1,
  rpcAccess: 2,
};

type SetupJournal = {
  app?: CreatedRpcApp;
  providerId?: string;
  providerAttached: boolean;
  providerSynced: boolean;
  skipped: boolean;
};

type SetupSummary = {
  appId: string;
  appName: string;
  providerConnected: boolean;
  errors: string[];
  skipped: boolean;
};

function apiErrorMessage(error: unknown, fallback: string): string {
  return isApiError(error) && error.message ? error.message : fallback;
}

function setupError(error: unknown): string {
  return isApiError(error) && error.message
    ? error.message
    : error instanceof Error
      ? error.message
      : "Unknown error";
}

/**
 * Full-page, three-step guided flow for creating an App:
 *
 *  1. **Project** — name the app.
 *  2. **Networks & chains** — pick the chains and networks to enable, listed
 *     from the client-side chain registry.
 *  3. **RPC access** — optionally select a Provider whose synchronized Endpoints
 *     are attached to matching Gateway routes by the server. New Providers are
 *     created through the account-wide dialog on that step, which writes
 *     immediately — a Provider is an account resource, not an App draft.
 *
 * No App is written until a create action on the final step. All three steps
 * hold pure local state until then, so leaving at any point — Cancel, the
 * sidebar, browser back — leaves no half-made app behind, and there's nothing
 * to warn about on exit.
 *
 * Finish is the single write path: it creates the app (which server-side also
 * provisions a gateway for every supported (chain, network) pair, all enabled,
 * and mints the first API key), then reconciles those gateways against the
 * selection, optionally associates the selected Provider, then triggers its
 * first synchronization. The API key remains available from App settings and
 * the Gateways key banner.
 */
export function CreateAppWizard() {
  const t = useTranslations("dashboard.apps");
  const tw = useTranslations("dashboard.apps.wizard");
  const [step, setStep] = useState<Step>("details");
  const [name, setName] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [providerId, setProviderId] = useState("");
  const [finishing, setFinishing] = useState(false);
  const [summary, setSummary] = useState<SetupSummary | null>(null);
  const journal = useRef<SetupJournal>({
    providerAttached: false,
    providerSynced: false,
    skipped: false,
  });

  const createMutation = useCreateAppMutation();
  const updateGateways = useBulkUpdateGatewaysMutation();

  const submitDetails = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim()) return;
    setStep("networks");
  };

  const toggleOne = (key: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  // Clicking a chain card selects every network in it, or clears them all when
  // the chain is already fully selected — the whole-chain analogue of toggleOne.
  const toggleChain = (keys: string[]) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (keys.every((key) => next.has(key))) {
        for (const key of keys) next.delete(key);
      } else {
        for (const key of keys) next.add(key);
      }
      return next;
    });

  const selectAll = () => setSelected(new Set(ALL_NETWORK_KEYS));
  const clearAll = () => setSelected(new Set());

  const finish = async (skipUpstream: boolean) => {
    if (selected.size === 0 || finishing) return;
    setFinishing(true);
    setSummary(null);
    const errors: string[] = [];
    const state = journal.current;
    state.skipped = skipUpstream;

    let app = state.app;
    try {
      if (!app) {
        app = await createMutation.mutateAsync({ name: name.trim(), enabled });
        state.app = app;
        toast.success(t("toast.created", { name: app.name }));
      }
    } catch (error) {
      toast.error(apiErrorMessage(error, t("toast.createError")));
      setFinishing(false);
      return;
    }

    const gateways = await listGateways({
      app_id: app.id,
      size: APP_GATEWAYS_SIZE,
      sort: "ASC",
    }).catch((error) => {
      errors.push(
        tw("summary.error", {
          scope: tw("summary.networks"),
          message: setupError(error),
        }),
      );
      return null;
    });

    if (gateways) {
      for (const desiredEnabled of [true, false]) {
        const targets = gateways.items.filter(
          (gateway) =>
            gateway.enabled !== desiredEnabled &&
            selected.has(networkKey(gateway.chain, gateway.network)) ===
              desiredEnabled,
        );
        if (targets.length === 0) continue;
        try {
          await updateGateways.mutateAsync({
            appId: app.id,
            enabled: desiredEnabled,
            gateways: targets.map((gateway) => ({
              id: gateway.id,
              expected_version: gateway.version,
            })),
          });
        } catch (error) {
          errors.push(
            tw("summary.error", {
              scope: tw("summary.networks"),
              message: setupError(error),
            }),
          );
        }
      }
    }

    if (skipUpstream) {
      setSummary({
        appId: app.id,
        appName: app.name,
        providerConnected: false,
        errors,
        skipped: true,
      });
      setFinishing(false);
      return;
    }

    if (!gateways || errors.length > 0) {
      setSummary({
        appId: app.id,
        appName: app.name,
        providerConnected: false,
        errors,
        skipped: false,
      });
      setFinishing(false);
      return;
    }

    try {
      if (!state.providerId) state.providerId = providerId;
      if (!state.providerAttached) {
        await setAppProvider(app.id, state.providerId);
        state.providerAttached = true;
      }
      if (!state.providerSynced) {
        const result = await syncProvider(state.providerId);
        state.providerSynced = result.status === "success";
        if (result.status !== "success") {
          errors.push(
            tw("summary.error", {
              scope: tw("summary.provider"),
              message: tw("summary.syncStatus", {
                status: result.status_label,
              }),
            }),
          );
        }
      }
    } catch (error) {
      errors.push(
        tw("summary.error", {
          scope: tw("summary.provider"),
          message: setupError(error),
        }),
      );
    }

    setSummary({
      appId: app.id,
      appName: app.name,
      providerConnected: state.providerAttached && state.providerSynced,
      errors,
      skipped: false,
    });
    setFinishing(false);
  };

  return (
    <div
      className={cn(
        "mx-auto flex w-full flex-col gap-8 pt-2",
        // The card grid needs more room than the single-column forms; widen the
        // whole flow on the network step so the chains lay out in a tidy grid.
        step === "details" ? "max-w-2xl" : "max-w-5xl",
      )}
    >
      <div className="flex flex-col gap-5">
        <div className="flex flex-col gap-1.5">
          <h1 className="text-3xl font-bold tracking-tight text-ink-900">
            {tw("title")}
          </h1>
          <p className="text-md text-ink-500">{tw("subtitle")}</p>
        </div>
        <Stepper currentStep={STEP_INDEX[step]}>
          <Stepper.Step>
            <Stepper.Indicator />
            <Stepper.Content>
              <Stepper.Title>{tw("steps.details.short")}</Stepper.Title>
            </Stepper.Content>
            <Stepper.Separator />
          </Stepper.Step>
          <Stepper.Step>
            <Stepper.Indicator />
            <Stepper.Content>
              <Stepper.Title>{tw("steps.networks.short")}</Stepper.Title>
            </Stepper.Content>
            <Stepper.Separator />
          </Stepper.Step>
          <Stepper.Step>
            <Stepper.Indicator />
            <Stepper.Content>
              <Stepper.Title>{tw("steps.rpcAccess.short")}</Stepper.Title>
            </Stepper.Content>
            <Stepper.Separator />
          </Stepper.Step>
        </Stepper>
      </div>

      {step === "details" ? (
        <form
          onSubmit={submitDetails}
          className="flex flex-col gap-6 rounded-2xl bg-surface p-6 shadow-section"
        >
          <div className="flex flex-col gap-1">
            <h2 className="text-lg font-semibold text-ink-900">
              {tw("steps.details.title")}
            </h2>
            <p className="text-sm text-ink-500">
              {tw("steps.details.subtitle")}
            </p>
          </div>
          <Field label={t("form.name")} htmlFor="app-name" required>
            <Input
              id="app-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t("form.namePlaceholder")}
              maxLength={128}
              autoFocus
            />
          </Field>
          <label
            htmlFor="app-enabled"
            className="flex items-center justify-between gap-4 rounded-md bg-ink-wash px-3 py-2.5"
          >
            <span className="text-md font-medium text-ink-900">
              {t("form.enabled")}
            </span>
            <Switch
              id="app-enabled"
              checked={enabled}
              onCheckedChange={setEnabled}
            />
          </label>
          <div className="flex justify-end gap-3">
            <Button type="button" variant="ghost" asChild>
              <Link href="/dashboard/apps">{tw("nav.cancel")}</Link>
            </Button>
            <Button type="submit" disabled={!name.trim()}>
              {tw("nav.next")}
            </Button>
          </div>
        </form>
      ) : null}

      {step === "networks" ? (
        <div className="flex flex-col gap-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex flex-col gap-1">
              <h2 className="text-lg font-semibold text-ink-900">
                {tw("steps.networks.title")}
              </h2>
              <p className="text-sm text-ink-500">
                {tw("steps.networks.subtitle")}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={selectAll}
                disabled={selected.size === ALL_NETWORK_KEYS.length}
              >
                {tw("networks.selectAll")}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={clearAll}
                disabled={selected.size === 0}
              >
                {tw("networks.clear")}
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {CHAIN_CATALOG.map((group) => (
              <ChainSelectCard
                key={group.chain}
                group={group}
                selected={selected}
                onToggleNetwork={toggleOne}
                onToggleChain={toggleChain}
              />
            ))}
          </div>

          <div className="flex items-center justify-between gap-3 rounded-2xl bg-surface px-5 py-4 shadow-section">
            <span className="text-sm text-ink-500">
              {selected.size === 0
                ? tw("networks.requireOne")
                : tw("networks.selectedCount", {
                    count: selected.size,
                    total: ALL_NETWORK_KEYS.length,
                  })}
            </span>
            <div className="flex items-center gap-3">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setStep("details")}
                disabled={finishing}
              >
                {tw("nav.back")}
              </Button>
              <Button
                type="button"
                onClick={() => setStep("rpcAccess")}
                disabled={selected.size === 0 || finishing}
              >
                {tw("nav.next")}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {step === "rpcAccess" && !summary ? (
        <div className="flex flex-col gap-5">
          <RpcAccessStep
            value={providerId}
            onChange={setProviderId}
            disabled={finishing}
          />
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-surface px-5 py-4 shadow-section">
            <p className="max-w-xl text-sm text-ink-500">
              {tw("rpcAccess.footerHint")}
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setStep("networks")}
                disabled={finishing}
              >
                {tw("nav.back")}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => finish(true)}
                disabled={finishing}
              >
                {finishing ? tw("nav.finishing") : tw("nav.skipCreate")}
              </Button>
              <Button
                type="button"
                onClick={() => finish(false)}
                disabled={finishing || !providerId}
              >
                {finishing ? tw("nav.finishing") : tw("nav.createConnect")}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {step === "rpcAccess" && summary ? (
        <section className="rounded-2xl bg-surface p-6 shadow-section">
          <div className="flex flex-col gap-2">
            <span className="text-sm font-semibold text-brand">
              {tw("summary.eyebrow")}
            </span>
            <h2 className="text-2xl font-bold text-ink-900">
              {tw("summary.title", { name: summary.appName })}
            </h2>
            <p className="text-sm text-ink-500">
              {summary.skipped
                ? tw("summary.skipped")
                : summary.providerConnected
                  ? tw("summary.providerConnected")
                  : tw("summary.providerPending")}
            </p>
          </div>

          {summary.errors.length > 0 ? (
            <div className="mt-5 rounded-xl bg-danger-soft p-4">
              <h3 className="text-sm font-semibold text-danger">
                {tw("summary.errorsTitle")}
              </h3>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-danger">
                {[...new Set(summary.errors)].map((error) => (
                  <li key={error}>{error}</li>
                ))}
              </ul>
            </div>
          ) : !summary.providerConnected ? (
            <p className="mt-5 rounded-xl bg-warning-soft p-4 text-sm text-warning">
              {tw("summary.providerPending")}
            </p>
          ) : (
            <p className="mt-5 rounded-xl bg-positive-soft p-4 text-sm text-positive">
              {tw("summary.complete")}
            </p>
          )}

          <div className="mt-6 flex flex-wrap justify-end gap-3">
            {summary.errors.length > 0 ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => finish(journal.current.skipped)}
                disabled={finishing}
              >
                {finishing ? tw("nav.finishing") : tw("summary.retry")}
              </Button>
            ) : null}
            <Button asChild>
              <Link href={`/dashboard/apps/${summary.appId}`}>
                {tw("summary.openApp")}
              </Link>
            </Button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
