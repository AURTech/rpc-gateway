"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { isApiError } from "@/api/client";
import type { RpcGatewayDetail } from "@/api/gateways/client";
import {
  HTTP_API_STRATEGY_TYPES,
  type HttpApiRoute,
  type HttpApiStrategyInput,
  type HttpApiStrategyType,
} from "@/api/http-api-routes/client";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useHttpApiRouteQuery,
  useReplaceHttpApiRouteMutation,
} from "@/hooks/use-http-api-routes";
import {
  clampWeight,
  type EndpointWeights,
  evenWeights,
  weightsValid,
} from "@/lib/endpoint-weights";

import { NewEndpointButton } from "../../endpoints/_components/new-endpoint-button";
import { EndpointPoolField } from "./endpoint-pool-field";
import { GatewaySectionGroup } from "./gateway-section";
import { RoutingModeCards } from "./routing-mode-cards";

const FORM_ID = "gateway-http-api-routing-form";

/** HTTP API routing has one gateway-wide route and no JSON-RPC method rules. */
export function HttpApiRoutingSection({
  gateway,
}: {
  gateway: RpcGatewayDetail;
}) {
  const t = useTranslations("dashboard.gateways");
  const routeQuery = useHttpApiRouteQuery(gateway.id);
  const replaceRoute = useReplaceHttpApiRouteMutation();

  const [seeded, setSeeded] = useState(false);
  const [seedVersion, setSeedVersion] = useState(0);
  const [endpointIds, setEndpointIds] = useState<string[]>([]);
  const [mode, setMode] = useState<HttpApiStrategyType>("priority_failover");
  const [weights, setWeights] = useState<EndpointWeights>({});

  const applyDraft = useCallback((route: HttpApiRoute) => {
    const targets = [...route.strategy.targets].sort(
      (left, right) => left.position - right.position,
    );
    setEndpointIds(targets.map((target) => target.endpoint_id));
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
    setSeedVersion(route.version);
    setSeeded(true);
  }, []);

  useEffect(() => {
    if (!routeQuery.data || seeded) return;
    applyDraft(routeQuery.data);
  }, [applyDraft, routeQuery.data, seeded]);

  const server = routeQuery.data;
  const serverIds = useMemo(
    () =>
      server
        ? [...server.strategy.targets]
            .sort((left, right) => left.position - right.position)
            .map((target) => target.endpoint_id)
        : [],
    [server],
  );
  const serverWeights = useMemo<EndpointWeights>(
    () =>
      server?.strategy.type === "load_balance"
        ? Object.fromEntries(
            server.strategy.targets.map((target) => [
              target.endpoint_id,
              target.weight,
            ]),
          )
        : {},
    [server],
  );

  const weighted = mode === "load_balance";
  const weightsOk = !weighted || weightsValid(endpointIds, weights);
  const dirty = server
    ? !sameOrder(endpointIds, serverIds) ||
      mode !== server.strategy.type ||
      (weighted && endpointIds.some((id) => weights[id] !== serverWeights[id]))
    : false;

  const handleModeChange = (next: HttpApiStrategyType) => {
    setMode(next);
    if (
      next === "load_balance" &&
      endpointIds.length > 0 &&
      !weightsValid(endpointIds, weights)
    ) {
      setWeights(evenWeights(endpointIds));
    }
  };

  const handlePoolChange = (next: string[]) => {
    setEndpointIds(next);
    if (mode !== "load_balance") return;
    setWeights((previous) => {
      const existing = next
        .map((id) => previous[id])
        .filter((weight): weight is number => Number.isFinite(weight));
      const fallback = existing.length > 0 ? Math.max(...existing) : 1;
      return Object.fromEntries(
        next.map((id) => [id, previous[id] ?? fallback]),
      );
    });
  };

  const cancelChanges = () => {
    if (server) applyDraft(server);
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!server || !dirty || !weightsOk || replaceRoute.isPending) return;
    replaceRoute.mutate(
      {
        gatewayId: gateway.id,
        input: {
          max_attempts: server.max_attempts,
          retry_policy: server.retry_policy,
          strategy: buildStrategy(mode, endpointIds, weights),
          expected_version: seedVersion,
        },
      },
      {
        onSuccess: (route) => {
          applyDraft(route);
          toast.success(t("toast.routingSaved"));
        },
        onError: (error) =>
          toast.error(
            isApiError(error) && error.message
              ? error.message
              : t("toast.routingError"),
          ),
      },
    );
  };

  return (
    <section className="flex flex-col gap-5">
      {routeQuery.isError ? (
        <p className="rounded-md bg-danger-soft px-3 py-3 text-sm text-danger">
          {t("httpApiRouting.error")}
        </p>
      ) : !seeded ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : (
        <form
          id={FORM_ID}
          onSubmit={handleSubmit}
          className="flex flex-col gap-5"
        >
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
                disabled={replaceRoute.isPending}
                initialChain={gateway.chain}
                initialNetwork={gateway.network}
                initialProtocol="http_api"
                presentation="dialog"
              />
            }
          >
            <RoutingModeCards
              value={mode}
              onChange={handleModeChange}
              options={HTTP_API_STRATEGY_TYPES.map((value) => ({
                value,
                label: t(`routingMode.${value}`),
                hint: t(`routingModeHint.${value}`),
              }))}
              ariaLabel={t("form.routingMode")}
              disabled={replaceRoute.isPending}
            />
            <EndpointPoolField
              chain={gateway.chain}
              network={gateway.network}
              protocol="http_api"
              embedded
              value={endpointIds}
              onChange={handlePoolChange}
              disabled={replaceRoute.isPending}
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
                  disabled={replaceRoute.isPending}
                >
                  {t("dialog.cancel")}
                </Button>
                <Button
                  type="submit"
                  disabled={!weightsOk || replaceRoute.isPending}
                >
                  {replaceRoute.isPending
                    ? t("dialog.saving")
                    : t("httpApiRouting.save")}
                </Button>
              </div>
            ) : null}
          </GatewaySectionGroup>
        </form>
      )}
    </section>
  );
}

function buildStrategy(
  mode: HttpApiStrategyType,
  endpointIds: readonly string[],
  weights: EndpointWeights,
): HttpApiStrategyInput {
  if (mode === "load_balance") {
    return {
      type: "load_balance",
      targets: endpointIds.map((endpointId) => ({
        endpoint_id: endpointId,
        weight: clampWeight(weights[endpointId]),
      })),
    };
  }
  return {
    type: "priority_failover",
    targets: endpointIds.map((endpointId) => ({ endpoint_id: endpointId })),
  };
}

function sameOrder(left: readonly string[], right: readonly string[]): boolean {
  return (
    left.length === right.length &&
    left.every((endpointId, index) => endpointId === right[index])
  );
}
