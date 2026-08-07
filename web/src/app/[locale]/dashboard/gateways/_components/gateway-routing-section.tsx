"use client";

import { Loader2, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { isApiError } from "@/api/client";
import type { RpcGatewayDetail } from "@/api/gateways/client";
import {
  JSONRPC_STRATEGY_TYPES,
  type JsonRpcRoute,
  type JsonRpcStrategyInput,
  type JsonRpcStrategyType,
} from "@/api/jsonrpc-routes/client";
import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCreateMethodRouteMutation,
  useDefaultRouteQuery,
  useDeleteMethodRouteMutation,
  useMethodRoutesQuery,
  useReplaceDefaultRouteMutation,
} from "@/hooks/use-routes";
import {
  clampWeight,
  type EndpointWeights,
  evenWeights,
  weightsValid,
} from "@/lib/endpoint-weights";
import { chainProtocol } from "@/lib/rpc-chain";

import { EndpointPoolField } from "./endpoint-pool-field";
import { GatewaySectionGroup } from "./gateway-section";
import { MethodMultiSelect } from "./method-multi-select";
import { RoutingModeCards } from "./routing-mode-cards";

/** Links the trailing submit button back to the editor form it belongs to. */
const FORM_ID = "gateway-routing-form";

/**
 * Merged "Routing" section — the gateway's default route and its per-method
 * rules share one editor (routing mode + endpoint pool), because a method rule
 * is just the same knob scoped to specific methods. A single OPTIONAL method
 * picker at the top decides which one you're editing:
 *
 * - **No method selected** → editing the DEFAULT route (all methods). Seed from
 *   the server route, track dirty state, and Save issues one `PUT /jsonrpc-route`
 *   with the full strategy; the route's policy fields are echoed back unchanged.
 * - **Methods selected** → CREATING a new rule for those methods. Rules are
 *   create + delete only, so Save POSTs a fresh rule, then the form resets back
 *   to the default.
 *
 * Below the picker, a list shows every method rule. Methods already owned by a
 * rule are excluded from the picker.
 */
export function GatewayRoutingSection({
  gateway,
}: {
  gateway: RpcGatewayDetail;
}) {
  const t = useTranslations("dashboard.gateways");
  const defaultRoute = useDefaultRouteQuery(gateway.id);
  const methodRoutes = useMethodRoutesQuery(gateway.id);
  const rules = methodRoutes.data?.items ?? [];

  const [seeded, setSeeded] = useState(false);
  const [seedKey, setSeedKey] = useState("");
  const [methods, setMethods] = useState<string[]>([]);
  const [endpointIds, setEndpointIds] = useState<string[]>([]);
  const [mode, setMode] = useState<JsonRpcStrategyType>("priority_failover");
  const [weights, setWeights] = useState<EndpointWeights>({});
  const [rulePendingDeletion, setRulePendingDeletion] =
    useState<JsonRpcRoute | null>(null);

  const replaceDefault = useReplaceDefaultRouteMutation();
  const createRule = useCreateMethodRouteMutation();
  const deleteRule = useDeleteMethodRouteMutation();

  // Empty method picker → editing the default route; otherwise creating a rule.
  const isDefault = methods.length === 0;

  // Methods already owned by a rule can't be reused — the server rejects them.
  const assigned = useMemo(
    () => new Set(rules.flatMap((r) => r.methods)),
    [rules],
  );

  const applyDraft = useCallback((route: JsonRpcRoute) => {
    const targets = sortedTargets(route);
    const ids = targets.map((target) => target.endpoint_id);
    setEndpointIds(ids);
    setSeedKey(membershipKey(ids));
    setMode(route.strategy.type);
    setWeights(
      route.strategy.type === "load_balance"
        ? Object.fromEntries(
            route.strategy.targets.map((target) => [
              target.endpoint_id,
              target.weight,
            ]),
          )
        : {},
    );
  }, []);

  // Seed the default draft from the server route once, then keep in-progress
  // edits across background refetches; reseed only when the SAVED membership
  // changes (which happens on our own save). Skip entirely while a rule draft is
  // on screen so a refetch never clobbers it.
  useEffect(() => {
    if (!isDefault) return;
    if (!defaultRoute.data) return;
    const ids = sortedTargets(defaultRoute.data).map((t) => t.endpoint_id);
    const nextKey = membershipKey(ids);
    if (seeded && nextKey === seedKey) return;
    applyDraft(defaultRoute.data);
    setSeeded(true);
  }, [defaultRoute.data, seeded, seedKey, isDefault, applyDraft]);

  const server = defaultRoute.data;
  const serverIds = useMemo(
    () => (server ? sortedTargets(server).map((t) => t.endpoint_id) : []),
    [server],
  );
  const serverMode = server?.strategy.type ?? "priority_failover";
  const serverWeights = useMemo<EndpointWeights>(
    () =>
      server && server.strategy.type === "load_balance"
        ? Object.fromEntries(
            server.strategy.targets.map((t) => [t.endpoint_id, t.weight]),
          )
        : {},
    [server],
  );

  const weighted = mode === "load_balance";
  const weightsOk = !weighted || weightsValid(endpointIds, weights);

  // Dirty tracking applies only to the default route (rules are create-only).
  const membershipDirty = !sameOrder(endpointIds, serverIds);
  const modeDirty = mode !== serverMode;
  const weightsDirty =
    weighted && endpointIds.some((id) => weights[id] !== serverWeights[id]);
  const dirty = membershipDirty || modeDirty || weightsDirty;

  const anyPending =
    replaceDefault.isPending || createRule.isPending || deleteRule.isPending;

  const canSaveDefault = dirty && weightsOk && !anyPending;
  const canCreateRule =
    methods.length > 0 && endpointIds.length > 0 && weightsOk && !anyPending;

  const handleModeChange = (next: JsonRpcStrategyType) => {
    setMode(next);
    // Seed an even split when weighting first applies to a non-empty pool.
    if (
      next === "load_balance" &&
      endpointIds.length > 0 &&
      !weightsValid(endpointIds, weights)
    ) {
      setWeights(evenWeights(endpointIds));
    }
  };

  // Keep the weight slots in sync with membership so a newly added endpoint
  // contributes to the weighted total (defaulting to a peer of existing ones).
  const handlePoolChange = (next: string[]) => {
    setEndpointIds(next);
    if (mode === "load_balance") {
      setWeights((prev) => {
        const existing = next
          .map((id) => prev[id])
          .filter((w): w is number => Number.isFinite(w));
        const fallback = existing.length > 0 ? Math.max(...existing) : 1;
        const out: EndpointWeights = {};
        for (const id of next) out[id] = prev[id] ?? fallback;
        return out;
      });
    }
  };

  // Swap the draft only when crossing the empty↔non-empty method boundary —
  // never mid-edit while adding a second method. Entering rule mode starts from
  // a blank rule; leaving it reseeds the default.
  const handleMethodsChange = (next: string[]) => {
    const wasDefault = methods.length === 0;
    const willDefault = next.length === 0;
    if (wasDefault && !willDefault) {
      setEndpointIds([]);
      setMode("priority_failover");
      setWeights({});
    } else if (!wasDefault && willDefault && defaultRoute.data) {
      applyDraft(defaultRoute.data);
    }
    setMethods(next);
  };

  const saveDefault = () => {
    if (!server) return;
    replaceDefault.mutate(
      {
        gatewayId: gateway.id,
        input: {
          minimum_trust: server.minimum_trust,
          max_latency_ms: server.max_latency_ms,
          max_attempts: server.max_attempts,
          retry_policy: server.retry_policy,
          strategy: buildStrategy(mode, endpointIds, weights),
          expected_version: server.version,
        },
      },
      {
        onSuccess: (route) => {
          applyDraft(route);
          toast.success(t("toast.routingSaved"));
        },
        onError: (err) =>
          toast.error(errorMessage(err, t("toast.routingError"))),
      },
    );
  };

  const createMethodRule = () => {
    createRule.mutate(
      {
        gatewayId: gateway.id,
        input: {
          methods,
          minimum_trust: server?.minimum_trust ?? "unverified",
          max_latency_ms: server?.max_latency_ms ?? null,
          max_attempts: server?.max_attempts ?? 3,
          retry_policy: server?.retry_policy ?? "safe_only",
          strategy: buildStrategy(mode, endpointIds, weights),
        },
      },
      {
        onSuccess: () => {
          toast.success(t("methodRoutes.toast.created"));
          setMethods([]);
          if (defaultRoute.data) applyDraft(defaultRoute.data);
        },
        onError: (err) =>
          toast.error(errorMessage(err, t("methodRoutes.toast.createError"))),
      },
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isDefault) {
      if (canSaveDefault) saveDefault();
    } else if (canCreateRule) {
      createMethodRule();
    }
  };

  const confirmDelete = () => {
    if (!rulePendingDeletion) return;
    deleteRule.mutate(
      {
        gatewayId: gateway.id,
        routeId: rulePendingDeletion.id,
        expectedVersion: rulePendingDeletion.version,
      },
      {
        onSuccess: () => {
          setRulePendingDeletion(null);
          toast.success(t("methodRoutes.toast.deleted"));
        },
        onError: (err) =>
          toast.error(errorMessage(err, t("methodRoutes.toast.deleteError"))),
      },
    );
  };

  return (
    <section className="flex flex-col gap-5">
      <header className="flex min-w-0 flex-col gap-1">
        <h2 className="text-xl font-bold tracking-tight text-ink-900">
          {t("routing.title")}
        </h2>
        <p className="text-sm text-ink-500">{t("routing.subtitle")}</p>
      </header>

      {!seeded ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          <form
            id={FORM_ID}
            onSubmit={handleSubmit}
            className="flex flex-col gap-5"
          >
            {/* The picker and the routes it can produce live in one group: the
             * list below is the same data the picker writes to, so splitting it
             * into its own section only added a heading to scroll past. */}
            <GatewaySectionGroup
              title={t("routing.methodsLabel")}
              description={t("routing.methodsHint")}
            >
              <div className="flex flex-col gap-3">
                <MethodMultiSelect
                  protocol={chainProtocol(gateway.chain)}
                  value={methods}
                  assigned={assigned}
                  onChange={handleMethodsChange}
                  disabled={anyPending}
                />

                {methodRoutes.isLoading ||
                methodRoutes.isError ||
                rules.length > 0 ? (
                  <ul className="flex flex-col divide-y divide-ink-wash border-t border-ink-wash">
                    {methodRoutes.isLoading ? (
                      <li className="flex flex-col gap-2 py-2">
                        <Skeleton className="h-12 w-full" />
                      </li>
                    ) : methodRoutes.isError ? (
                      <li className="py-4 text-center text-md text-ink-500">
                        {t("error.title")}
                      </li>
                    ) : (
                      rules.map((rule) => (
                        <RuleRow
                          key={rule.id}
                          rule={rule}
                          pending={
                            deleteRule.isPending &&
                            rulePendingDeletion?.id === rule.id
                          }
                          disabled={anyPending}
                          onDelete={() => setRulePendingDeletion(rule)}
                        />
                      ))
                    )}
                  </ul>
                ) : null}
              </div>
            </GatewaySectionGroup>

            <GatewaySectionGroup
              title={t("form.routingMode")}
              description={t(`routingModeHint.${mode}`)}
            >
              <RoutingModeCards
                value={mode}
                onChange={handleModeChange}
                options={JSONRPC_STRATEGY_TYPES.map((value) => ({
                  value,
                  label: t(`routingMode.${value}`),
                  hint: t(`routingModeHint.${value}`),
                }))}
                ariaLabel={t("form.routingMode")}
                disabled={anyPending}
              />
            </GatewaySectionGroup>

            <EndpointPoolField
              chain={gateway.chain}
              network={gateway.network}
              title={
                isDefault
                  ? t("endpointTable.defaultTitle")
                  : t("endpointTable.ruleTitle")
              }
              description={
                isDefault
                  ? t("endpointTable.defaultDescription")
                  : t("endpointTable.ruleDescription")
              }
              value={endpointIds}
              onChange={handlePoolChange}
              disabled={anyPending}
              weighted={weighted}
              weights={weights}
              onWeightChange={(id, value) =>
                setWeights((prev) => ({ ...prev, [id]: value }))
              }
            />
          </form>

          {/* The submit action closes the whole section rather than sitting
           * mid-form, so it reads as "apply this configuration" at the content
           * area's bottom-right. `form` ties it back to the editor above. */}
          {isDefault ? (
            dirty ? (
              <div className="flex justify-end">
                <Button form={FORM_ID} type="submit" disabled={!canSaveDefault}>
                  {replaceDefault.isPending
                    ? t("dialog.saving")
                    : t("routing.saveDefault")}
                </Button>
              </div>
            ) : null
          ) : (
            <div className="flex justify-end">
              <Button form={FORM_ID} type="submit" disabled={!canCreateRule}>
                {createRule.isPending
                  ? t("dialog.saving")
                  : t("routing.addRule")}
              </Button>
            </div>
          )}
        </div>
      )}

      <ConfirmDialog
        open={rulePendingDeletion !== null}
        onOpenChange={(open) => {
          if (!open) setRulePendingDeletion(null);
        }}
        title={t("methodRoutes.deleteDialog.title")}
        description={
          rulePendingDeletion
            ? t("methodRoutes.deleteDialog.body", {
                methods: rulePendingDeletion.methods.join(", "),
              })
            : undefined
        }
        icon={<Trash2 />}
        onConfirm={confirmDelete}
        confirmLabel={t("methodRoutes.deleteDialog.confirm")}
        confirmingLabel={t("methodRoutes.deleteDialog.confirming")}
        cancelLabel={t("dialog.cancel")}
        confirming={deleteRule.isPending}
        contentClassName="sm:max-w-dialog"
      />
    </section>
  );
}

function RuleRow({
  rule,
  pending,
  disabled,
  onDelete,
}: {
  rule: JsonRpcRoute;
  pending: boolean;
  disabled?: boolean;
  onDelete: () => void;
}) {
  const t = useTranslations("dashboard.gateways");
  const endpointCount = rule.strategy.targets.length;
  const isWeighted = rule.strategy.type === "load_balance";

  return (
    <li className="flex items-start gap-2 py-2.5">
      <div className="min-w-0 flex-1">
        <ul className="flex flex-wrap gap-1">
          {rule.methods.map((m) => (
            <li
              key={m}
              className="rounded-full bg-ink-wash px-2 py-0.5 font-mono text-2xs font-medium text-ink-700"
            >
              {m}
            </li>
          ))}
        </ul>
        <p className="mt-1.5 text-2xs text-ink-400">
          {t(`routingMode.${rule.strategy.type}`)}
          {" · "}
          {t("methodRoutes.usesEndpoints", { count: endpointCount })}
          {isWeighted ? ` · ${t("weights.badge")}` : ""}
        </p>
      </div>
      <button
        type="button"
        aria-label={t("methodRoutes.form.deleteRule")}
        onClick={onDelete}
        disabled={disabled || pending}
        className="inline-flex size-7 shrink-0 items-center justify-center rounded-md text-ink-400 transition-colors hover:bg-danger-soft hover:text-danger focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger/40 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {pending ? (
          <Loader2 className="size-4 animate-spin" aria-hidden />
        ) : (
          <Trash2 className="size-4" aria-hidden />
        )}
      </button>
    </li>
  );
}

/** Targets ordered by their persisted `position` (the failover sequence). */
function sortedTargets(route: JsonRpcRoute) {
  return [...route.strategy.targets].sort((a, b) => a.position - b.position);
}

function buildStrategy(
  mode: JsonRpcStrategyType,
  ids: readonly string[],
  weights: EndpointWeights,
): JsonRpcStrategyInput {
  if (mode === "load_balance") {
    return {
      type: "load_balance",
      targets: ids.map((id) => ({
        endpoint_id: id,
        weight: clampWeight(weights[id]),
      })),
    };
  }
  return {
    type: "priority_failover",
    targets: ids.map((id) => ({ endpoint_id: id })),
  };
}

function sameOrder(left: readonly string[], right: readonly string[]): boolean {
  return (
    left.length === right.length &&
    left.every((id, index) => id === right[index])
  );
}

function membershipKey(ids: readonly string[]): string {
  return JSON.stringify(ids);
}

function errorMessage(err: unknown, fallback: string): string {
  return isApiError(err) && err.message ? err.message : fallback;
}
