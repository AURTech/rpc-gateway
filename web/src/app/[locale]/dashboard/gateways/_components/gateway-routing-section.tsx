"use client";

import { Plus, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import {
  type Ref,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
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
import { useMotionPreset } from "@/hooks/use-motion-preset";
import {
  useCreateMethodRouteMutation,
  useDefaultRouteQuery,
  useDeleteMethodRouteMutation,
  useMethodRoutesQuery,
  useReplaceDefaultRouteMutation,
  useUpdateMethodRouteMutation,
} from "@/hooks/use-routes";
import {
  clampWeight,
  type EndpointWeights,
  evenWeights,
  weightsValid,
} from "@/lib/endpoint-weights";
import { chainProtocol } from "@/lib/rpc-chain";

import { NewEndpointButton } from "../../endpoints/_components/new-endpoint-button";
import { EndpointPoolField } from "./endpoint-pool-field";
import { GatewaySectionGroup } from "./gateway-section";
import { MethodMultiSelect } from "./method-multi-select";
import { RoutingModeCards } from "./routing-mode-cards";

const DEFAULT_FORM_ID = "gateway-default-routing-form";

export function GatewayRoutingSection({
  gateway,
}: {
  gateway: RpcGatewayDetail;
}) {
  const t = useTranslations("dashboard.gateways");
  const defaultRoute = useDefaultRouteQuery(gateway.id);
  const methodRoutes = useMethodRoutesQuery(gateway.id);

  return (
    <section className="flex flex-col gap-6">
      {defaultRoute.isLoading ? (
        <Skeleton className="h-72 w-full" />
      ) : defaultRoute.isError || !defaultRoute.data ? (
        <p className="rounded-2xl bg-danger-soft px-4 py-6 text-sm text-danger">
          {t("error.title")}
        </p>
      ) : (
        <DefaultRouteEditor gateway={gateway} route={defaultRoute.data} />
      )}

      <MethodRuleWorkbench
        gateway={gateway}
        defaultRoute={defaultRoute.data ?? null}
        rules={methodRoutes.data?.items ?? []}
        loading={methodRoutes.isLoading}
        failed={methodRoutes.isError}
      />
    </section>
  );
}

function DefaultRouteEditor({
  gateway,
  route,
}: {
  gateway: RpcGatewayDetail;
  route: JsonRpcRoute;
}) {
  const t = useTranslations("dashboard.gateways");
  const replaceDefault = useReplaceDefaultRouteMutation();
  const [loadedVersion, setLoadedVersion] = useState(0);
  const [endpointIds, setEndpointIds] = useState<string[]>([]);
  const [mode, setMode] = useState<JsonRpcStrategyType>("priority_failover");
  const [weights, setWeights] = useState<EndpointWeights>({});

  const applyRoute = useCallback((value: JsonRpcRoute) => {
    const targets = sortedTargets(value);
    setEndpointIds(targets.map((target) => target.endpoint_id));
    setMode(value.strategy.type);
    setWeights(routeWeights(value));
    setLoadedVersion(value.version);
  }, []);

  useEffect(() => {
    if (loadedVersion === route.version) return;
    applyRoute(route);
  }, [applyRoute, loadedVersion, route]);

  const serverIds = useMemo(
    () => sortedTargets(route).map((target) => target.endpoint_id),
    [route],
  );
  const serverWeights = useMemo(() => routeWeights(route), [route]);
  const weighted = mode === "load_balance";
  const weightsOk = !weighted || weightsValid(endpointIds, weights);
  const dirty =
    !sameOrder(endpointIds, serverIds) ||
    mode !== route.strategy.type ||
    (weighted && endpointIds.some((id) => weights[id] !== serverWeights[id]));
  const canSave = dirty && weightsOk && !replaceDefault.isPending;

  const handleModeChange = (next: JsonRpcStrategyType) => {
    setMode(next);
    if (next === "load_balance" && !weightsValid(endpointIds, weights)) {
      setWeights(evenWeights(endpointIds));
    }
  };

  const handlePoolChange = (next: string[]) => {
    setEndpointIds(next);
    if (mode === "load_balance") setWeights(fillWeights(next, weights));
  };

  const cancelChanges = () => applyRoute(route);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSave) return;
    replaceDefault.mutate(
      {
        gatewayId: gateway.id,
        input: {
          max_attempts: route.max_attempts,
          retry_policy: route.retry_policy,
          strategy: buildStrategy(mode, endpointIds, weights),
          expected_version: route.version,
        },
      },
      {
        onSuccess: (saved) => {
          applyRoute(saved);
          toast.success(t("toast.routingSaved"));
        },
        onError: (error) =>
          toast.error(errorMessage(error, t("toast.routingError"))),
      },
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <form id={DEFAULT_FORM_ID} onSubmit={submit} className="flex flex-col">
        <GatewaySectionGroup
          title={t("routing.title")}
          description={t("routing.description")}
          bodyClassName="flex flex-col gap-4"
          action={
            <NewEndpointButton
              label={t("endpointTable.createEndpoint")}
              size="sm"
              variant="soft"
              showIcon={false}
              className="rounded-xl"
              disabled={replaceDefault.isPending}
              initialChain={gateway.chain}
              initialNetwork={gateway.network}
              initialProtocol="jsonrpc"
              presentation="dialog"
            />
          }
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
            disabled={replaceDefault.isPending}
          />
          <EndpointPoolField
            chain={gateway.chain}
            network={gateway.network}
            embedded
            value={endpointIds}
            onChange={handlePoolChange}
            disabled={replaceDefault.isPending}
            weighted={weighted}
            weights={weights}
            onWeightChange={(id, value) =>
              setWeights((previous) => ({ ...previous, [id]: value }))
            }
          />
          {dirty ? (
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                onClick={cancelChanges}
                disabled={replaceDefault.isPending}
              >
                {t("dialog.cancel")}
              </Button>
              <Button type="submit" disabled={!canSave}>
                {replaceDefault.isPending
                  ? t("dialog.saving")
                  : t("routing.saveDefault")}
              </Button>
            </div>
          ) : null}
        </GatewaySectionGroup>
      </form>
    </div>
  );
}

function MethodRuleWorkbench({
  gateway,
  defaultRoute,
  rules,
  loading,
  failed,
}: {
  gateway: RpcGatewayDetail;
  defaultRoute: JsonRpcRoute | null;
  rules: JsonRpcRoute[];
  loading: boolean;
  failed: boolean;
}) {
  const t = useTranslations("dashboard.gateways");
  const [creating, setCreating] = useState(false);
  const newRuleRef = useRef<HTMLLIElement>(null);
  const newRuleInputRef = useRef<HTMLInputElement>(null);
  const motionPreset = useMotionPreset();
  const assignedMethods = useMemo(
    () => new Set(rules.flatMap((rule) => rule.methods)),
    [rules],
  );

  useEffect(() => {
    if (!creating) return;

    const frame = requestAnimationFrame(() => {
      const editor = newRuleRef.current;
      if (!editor) return;

      newRuleInputRef.current?.focus({ preventScroll: true });

      const bounds = editor.getBoundingClientRect();
      const outsideViewport =
        bounds.top < 0 || bounds.bottom > window.innerHeight;
      if (!outsideViewport) return;

      editor.scrollIntoView({
        behavior: motionPreset.reduce ? "auto" : "smooth",
        block: "start",
      });
    });

    return () => cancelAnimationFrame(frame);
  }, [creating, motionPreset.reduce]);

  return (
    <section className="flex flex-col gap-4">
      <GatewaySectionGroup
        title={t("methodWorkbench.title")}
        description={t("methodWorkbench.description")}
        insetBody={false}
        action={
          rules.length > 0 || creating ? (
            <Button
              type="button"
              size="sm"
              variant="soft"
              className="rounded-xl"
              onClick={() => setCreating(true)}
              disabled={creating || defaultRoute === null}
            >
              <Plus aria-hidden />
              {t("methodWorkbench.addNewRule")}
            </Button>
          ) : null
        }
      >
        {loading ? (
          <div className="flex flex-col gap-3 px-4 pb-4">
            <Skeleton className="h-72 w-full rounded-2xl" />
            <Skeleton className="h-72 w-full rounded-2xl" />
          </div>
        ) : failed ? (
          <p className="mx-4 mb-4 rounded-2xl bg-surface py-4 text-center text-sm text-danger">
            {t("methodWorkbench.loadError")}
          </p>
        ) : rules.length === 0 && !creating ? (
          <div className="mx-4 mb-4 flex flex-col items-center gap-3 rounded-2xl bg-surface px-4 py-10 text-center">
            <div className="flex max-w-md flex-col gap-1">
              <p className="text-sm font-semibold text-ink-700">
                {t("methodWorkbench.emptyTitle")}
              </p>
              <p className="text-sm text-ink-500">
                {t("methodWorkbench.noRules")}
              </p>
            </div>
            <Button
              type="button"
              size="sm"
              variant="soft"
              className="rounded-xl"
              onClick={() => setCreating(true)}
              disabled={defaultRoute === null}
            >
              <Plus aria-hidden />
              {t("methodWorkbench.addNewRule")}
            </Button>
          </div>
        ) : (
          <ul className="flex flex-col gap-4 px-4 pb-4">
            {rules.map((rule) => (
              <li key={rule.id}>
                <MethodRuleEditor
                  gateway={gateway}
                  route={rule}
                  seedRoute={rule}
                  assigned={
                    new Set(
                      [...assignedMethods].filter(
                        (method) => !rule.methods.includes(method),
                      ),
                    )
                  }
                />
              </li>
            ))}
            {creating && defaultRoute ? (
              <li ref={newRuleRef} className="scroll-mt-24 sm:scroll-mt-8">
                <MethodRuleEditor
                  gateway={gateway}
                  route={null}
                  seedRoute={defaultRoute}
                  assigned={assignedMethods}
                  methodInputRef={newRuleInputRef}
                  onCancel={() => setCreating(false)}
                  onCreated={() => setCreating(false)}
                />
              </li>
            ) : null}
          </ul>
        )}
      </GatewaySectionGroup>
    </section>
  );
}

function MethodRuleEditor({
  gateway,
  route,
  seedRoute,
  assigned,
  methodInputRef,
  onCancel,
  onCreated,
}: {
  gateway: RpcGatewayDetail;
  route: JsonRpcRoute | null;
  seedRoute: JsonRpcRoute;
  assigned: ReadonlySet<string>;
  methodInputRef?: Ref<HTMLInputElement>;
  onCancel?: () => void;
  onCreated?: () => void;
}) {
  const t = useTranslations("dashboard.gateways");
  const createRule = useCreateMethodRouteMutation();
  const updateRule = useUpdateMethodRouteMutation();
  const deleteRule = useDeleteMethodRouteMutation();
  const [loadedVersion, setLoadedVersion] = useState(0);
  const [methods, setMethods] = useState<string[]>([]);
  const [endpointIds, setEndpointIds] = useState<string[]>([]);
  const [mode, setMode] = useState<JsonRpcStrategyType>("priority_failover");
  const [weights, setWeights] = useState<EndpointWeights>({});
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const applyRoute = useCallback(
    (value: JsonRpcRoute, nextMethods = value.methods) => {
      setMethods(nextMethods);
      setEndpointIds(sortedTargets(value).map((target) => target.endpoint_id));
      setMode(value.strategy.type);
      setWeights(routeWeights(value));
      setLoadedVersion(value.version);
    },
    [],
  );

  useEffect(() => {
    if (loadedVersion === seedRoute.version) return;
    applyRoute(seedRoute, route ? route.methods : []);
  }, [applyRoute, loadedVersion, route, seedRoute]);

  const savedIds = useMemo(
    () => sortedTargets(seedRoute).map((target) => target.endpoint_id),
    [seedRoute],
  );
  const savedWeights = useMemo(() => routeWeights(seedRoute), [seedRoute]);
  const weighted = mode === "load_balance";
  const weightsOk = !weighted || weightsValid(endpointIds, weights);
  const creating = route === null;
  const dirty = creating
    ? methods.length > 0
    : !sameMembers(methods, route.methods) ||
      !sameOrder(endpointIds, savedIds) ||
      mode !== route.strategy.type ||
      (weighted && endpointIds.some((id) => weights[id] !== savedWeights[id]));
  const pending =
    createRule.isPending || updateRule.isPending || deleteRule.isPending;
  const canSave =
    dirty &&
    methods.length > 0 &&
    endpointIds.length > 0 &&
    weightsOk &&
    !pending;

  const handleModeChange = (next: JsonRpcStrategyType) => {
    setMode(next);
    if (next === "load_balance" && !weightsValid(endpointIds, weights)) {
      setWeights(evenWeights(endpointIds));
    }
  };

  const handleEndpointChange = (next: string[]) => {
    setEndpointIds(next);
    if (mode === "load_balance") setWeights(fillWeights(next, weights));
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSave) return;
    const values = {
      methods,
      max_attempts: seedRoute.max_attempts,
      retry_policy: seedRoute.retry_policy,
      strategy: buildStrategy(mode, endpointIds, weights),
    };
    if (creating) {
      createRule.mutate(
        { gatewayId: gateway.id, input: values },
        {
          onSuccess: () => {
            toast.success(t("methodRoutes.toast.created"));
            onCreated?.();
          },
          onError: (error) =>
            toast.error(
              errorMessage(error, t("methodRoutes.toast.createError")),
            ),
        },
      );
      return;
    }
    updateRule.mutate(
      {
        gatewayId: gateway.id,
        routeId: route.id,
        input: { ...values, expected_version: route.version },
      },
      {
        onSuccess: (saved) => {
          applyRoute(saved);
          toast.success(t("methodRoutes.toast.updated"));
        },
        onError: (error) =>
          toast.error(errorMessage(error, t("methodRoutes.toast.updateError"))),
      },
    );
  };

  const confirmDelete = () => {
    if (!route) return;
    deleteRule.mutate(
      {
        gatewayId: gateway.id,
        routeId: route.id,
        expectedVersion: route.version,
      },
      {
        onSuccess: () => {
          setConfirmingDelete(false);
          toast.success(t("methodRoutes.toast.deleted"));
        },
        onError: (error) =>
          toast.error(errorMessage(error, t("methodRoutes.toast.deleteError"))),
      },
    );
  };

  const reset = () => {
    if (creating) onCancel?.();
    else applyRoute(route);
  };

  const formId = `gateway-method-rule-form-${route?.id ?? "new"}`;

  return (
    <div className="rounded-2xl bg-surface p-4 sm:p-5">
      <form id={formId} onSubmit={submit} className="flex flex-col gap-5">
        <MethodMultiSelect
          protocol={chainProtocol(gateway.chain)}
          value={methods}
          assigned={assigned}
          onChange={setMethods}
          disabled={pending}
          inputRef={methodInputRef}
        />

        <RoutingModeCards
          value={mode}
          onChange={handleModeChange}
          options={JSONRPC_STRATEGY_TYPES.map((value) => ({
            value,
            label: t(`routingMode.${value}`),
            hint: t(`routingModeHint.${value}`),
          }))}
          ariaLabel={t("form.routingMode")}
          disabled={pending}
        />

        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="pl-1">
              <h4 className="text-sm font-semibold text-ink-900">
                {t("endpointTable.title")}
              </h4>
              <p className="mt-0.5 text-2xs text-ink-500">
                {t("endpointTable.ruleDescription")}
              </p>
            </div>
            <NewEndpointButton
              label={t("endpointTable.createEndpoint")}
              size="sm"
              variant="soft"
              showIcon={false}
              className="rounded-xl"
              disabled={pending}
              initialChain={gateway.chain}
              initialNetwork={gateway.network}
              initialProtocol="jsonrpc"
              presentation="dialog"
            />
          </div>
          <EndpointPoolField
            chain={gateway.chain}
            network={gateway.network}
            embedded
            value={endpointIds}
            onChange={handleEndpointChange}
            disabled={pending}
            weighted={weighted}
            weights={weights}
            onWeightChange={(id, value) =>
              setWeights((previous) => ({ ...previous, [id]: value }))
            }
          />
        </div>

        <div className="flex items-center justify-between gap-3">
          {route ? (
            <Button
              type="button"
              variant="ghost"
              className="text-danger hover:bg-danger-soft hover:text-danger"
              onClick={() => setConfirmingDelete(true)}
              disabled={pending}
            >
              <Trash2 aria-hidden />
              {t("methodRoutes.form.deleteRule")}
            </Button>
          ) : (
            <span />
          )}
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={reset}
              disabled={pending || (!creating && !dirty)}
            >
              {creating ? t("dialog.cancel") : t("methodRoutes.form.reset")}
            </Button>
            <Button type="submit" disabled={!canSave}>
              {pending
                ? t("dialog.saving")
                : creating
                  ? t("routing.addRule")
                  : t("routing.saveRule")}
            </Button>
          </div>
        </div>
      </form>

      <ConfirmDialog
        open={confirmingDelete}
        onOpenChange={setConfirmingDelete}
        title={t("methodRoutes.deleteDialog.title")}
        description={
          route
            ? t("methodRoutes.deleteDialog.body", {
                methods: route.methods.join(", "),
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
    </div>
  );
}

function sortedTargets(route: JsonRpcRoute) {
  return [...route.strategy.targets].sort(
    (left, right) => left.position - right.position,
  );
}

function routeWeights(route: JsonRpcRoute): EndpointWeights {
  return route.strategy.type === "load_balance"
    ? Object.fromEntries(
        route.strategy.targets.map((target) => [
          target.endpoint_id,
          target.weight,
        ]),
      )
    : {};
}

function fillWeights(
  ids: string[],
  previous: EndpointWeights,
): EndpointWeights {
  const existing = ids
    .map((id) => previous[id])
    .filter((weight): weight is number => Number.isFinite(weight));
  const fallback = existing.length > 0 ? Math.max(...existing) : 1;
  return Object.fromEntries(ids.map((id) => [id, previous[id] ?? fallback]));
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

function sameMembers(
  left: readonly string[],
  right: readonly string[],
): boolean {
  if (left.length !== right.length) return false;
  const seen = new Set(right);
  return left.every((value) => seen.has(value));
}

function errorMessage(error: unknown, fallback: string): string {
  return isApiError(error) && error.message ? error.message : fallback;
}
