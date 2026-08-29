"use client";

import { AlertTriangleIcon, CheckCircle2Icon } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
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
import { useMotionPreset } from "@/hooks/use-motion-preset";
import { Link, useRouter } from "@/i18n/navigation";
import { transitionEnter, wizardStepVariants } from "@/lib/motion";

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
  errors: string[];
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
  const router = useRouter();
  const motionPreset = useMotionPreset();
  const [step, setStep] = useState<Step>("details");
  // +1 advancing, -1 going back. Drives which way the panels slide, so a "Back"
  // button reverses the motion instead of repeating the forward one.
  const [stepDirection, setStepDirection] = useState(1);
  const goToStep = (next: Step) => {
    setStepDirection(STEP_INDEX[next] >= STEP_INDEX[step] ? 1 : -1);
    setStep(next);
  };
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
    goToStep("networks");
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
      if (errors.length === 0) {
        router.replace(`/dashboard/apps/${app.id}`);
        return;
      }
      setSummary({
        appId: app.id,
        appName: app.name,
        errors,
      });
      setFinishing(false);
      return;
    }

    if (!gateways || errors.length > 0) {
      setSummary({
        appId: app.id,
        appName: app.name,
        errors,
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
        // Provider discovery is a durable background run. Acceptance means the
        // run was queued; its final outcome remains visible from Connections.
        await syncProvider(state.providerId);
        state.providerSynced = true;
      }
    } catch (error) {
      errors.push(
        tw("summary.error", {
          scope: tw("summary.provider"),
          message: setupError(error),
        }),
      );
    }

    if (errors.length === 0) {
      router.replace(`/dashboard/apps/${app.id}`);
    } else {
      setSummary({
        appId: app.id,
        appName: app.name,
        errors,
      });
      setFinishing(false);
    }
  };

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 pt-2">
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

      {/* One panel is on screen at a time, so mode="wait" is what keeps the
          outgoing step from overlapping the incoming one mid-slide. `custom`
          carries the direction into the variants so Back reverses the travel.
          The summary replaces the last step in place, hence its own key. */}
      <AnimatePresence mode="wait" initial={false} custom={stepDirection}>
        <motion.div
          key={summary ? "summary" : step}
          custom={stepDirection}
          variants={wizardStepVariants}
          initial={motionPreset.initial("initial")}
          animate="animate"
          exit="exit"
          transition={motionPreset.transition(transitionEnter)}
        >
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
                    onClick={() => goToStep("details")}
                    disabled={finishing}
                  >
                    {tw("nav.back")}
                  </Button>
                  <Button
                    type="button"
                    onClick={() => goToStep("rpcAccess")}
                    disabled={selected.size === 0 || finishing}
                  >
                    {tw("nav.next")}
                  </Button>
                </div>
              </div>
            </div>
          ) : null}

          {step === "rpcAccess" && !summary ? (
            <RpcAccessStep
              value={providerId}
              onChange={setProviderId}
              disabled={finishing}
              footer={
                <div className="flex flex-wrap items-center justify-end gap-3">
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => goToStep("networks")}
                    disabled={finishing}
                  >
                    {tw("nav.back")}
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
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
              }
            />
          ) : null}

          {step === "rpcAccess" && summary ? (
            <section className="rounded-2xl bg-surface p-6 shadow-section">
              <output className="flex items-start gap-3">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-positive-soft text-positive">
                  <CheckCircle2Icon className="size-5" aria-hidden />
                </span>
                <div className="min-w-0">
                  <h2 className="text-2xl font-bold text-ink-900">
                    {tw("summary.title", { name: summary.appName })}
                  </h2>
                  <p className="mt-1 text-sm text-ink-500">
                    {tw("summary.description")}
                  </p>
                </div>
              </output>

              <div className="mt-6 divide-y divide-table-frame">
                <div className="flex items-start gap-3 pb-4">
                  <CheckCircle2Icon
                    className="mt-0.5 size-5 shrink-0 text-positive"
                    aria-hidden
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-4">
                      <h3 className="text-sm font-semibold text-ink-900">
                        {tw("summary.app")}
                      </h3>
                      <span className="text-sm font-semibold text-positive">
                        {tw("summary.created")}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-ink-500">
                      {tw("summary.appReady")}
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3 pt-4" role="alert">
                  <AlertTriangleIcon
                    className="mt-0.5 size-5 shrink-0 text-warning"
                    aria-hidden
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-4">
                      <h3 className="text-sm font-semibold text-ink-900">
                        {tw("summary.remainingSetup")}
                      </h3>
                      <span className="text-sm font-semibold text-warning">
                        {tw("summary.needsAttention")}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-ink-500">
                      {tw("summary.setupDescription")}
                    </p>
                    <ul className="mt-3 list-disc space-y-1.5 pl-4 text-sm text-ink-700">
                      {[...new Set(summary.errors)].map((error) => (
                        <li key={error}>{error}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>

              <div className="mt-6 flex flex-wrap justify-end gap-3">
                <Button variant="ghost" asChild>
                  <Link href={`/dashboard/apps/${summary.appId}`}>
                    {tw("summary.openApp")}
                  </Link>
                </Button>
                <Button
                  type="button"
                  onClick={() => finish(journal.current.skipped)}
                  disabled={finishing}
                >
                  {finishing ? tw("nav.finishing") : tw("summary.retry")}
                </Button>
              </div>
            </section>
          ) : null}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
