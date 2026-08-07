"use client";

import { ArrowDownIcon, ArrowUpIcon, Trash2Icon } from "lucide-react";
import { useTranslations } from "next-intl";
import { type ReactNode, useState } from "react";

import type { Endpoint, EndpointProtocol } from "@/api/endpoints/client";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useEndpointsQuery } from "@/hooks/use-endpoints";
import type { Chain, Network } from "@/lib/blockchain";
import {
  type EndpointWeights,
  isValidWeight,
  sharePercents,
  weightsValid,
} from "@/lib/endpoint-weights";
import {
  chainLabel,
  networkLabel,
  type RpcChain,
  type RpcNetwork,
} from "@/lib/rpc-chain";
import { cn } from "@/lib/utils";

import { DeleteEndpointDialog } from "../../endpoints/_components/delete-endpoint-dialog";
import { NewEndpointButton } from "../../endpoints/_components/new-endpoint-button";
import { WeightRatioInput, WeightShare } from "./endpoint-weight-controls";

const ENDPOINT_FETCH_SIZE = 50;

/**
 * Ordered endpoint pool editor shared by the gateway default route and method
 * routing rules. Row order among the enabled rows is submission order — it
 * becomes the persisted `position`, the failover sequence under priority
 * routing.
 *
 * One shape for every caller: a titled gray frame (matching GatewaySectionGroup)
 * wrapping a single table listing EVERY endpoint for this chain/network. A
 * per-row switch turns an endpoint on for this gateway, so assigning and
 * unassigning happen in place — no tab to switch back to. Enabled rows sort
 * above the rest in pool order; disabled rows keep their controls visible but
 * inert. When `weighted` is on, an extra column exposes each row's raw weight
 * input (1–1000, the API `weight`) plus a read-only % share preview.
 *
 * Endpoints come from the account-global registry, filtered to this gateway's
 * chain/network and the route protocol selected by the caller.
 */
export function EndpointPoolField({
  chain,
  network,
  protocol = "jsonrpc",
  title,
  description,
  value,
  onChange,
  disabled,
  weighted = false,
  weights,
  onWeightChange,
}: {
  chain: RpcChain;
  network: RpcNetwork;
  protocol?: EndpointProtocol;
  /** Sub-group heading — the pool serves both the default route and rules. */
  title: string;
  description?: string;
  value: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
  weighted?: boolean;
  weights?: EndpointWeights;
  onWeightChange?: (id: string, value: number) => void;
}) {
  const t = useTranslations("dashboard.gateways");
  const [deleteTarget, setDeleteTarget] = useState<Endpoint | null>(null);
  // The gateway and endpoint chain/network enums share identical members.
  const { data, isLoading, isError } = useEndpointsQuery({
    chain: [chain as Chain],
    network: [network as Network],
    protocol,
    enabled: true,
    size: ENDPOINT_FETCH_SIZE,
  });

  const endpoints = data?.items ?? [];
  const byId = new Map<string, Endpoint>(endpoints.map((e) => [e.id, e]));
  const normalizedShares =
    weighted && weights && weightsValid(value, weights)
      ? sharePercents(value, weights)
      : {};

  if (isLoading) return null;
  if (isError) {
    return (
      <p className="rounded-md bg-danger-soft px-3 py-3 text-sm text-danger">
        {t("form.endpointsError")}
      </p>
    );
  }

  // Enabled endpoints first, in pool order; the rest keep registry order below.
  // A pooled id with no registry match still gets a row so it stays removable.
  const rows: { id: string; endpoint: Endpoint | undefined }[] = [
    ...value.map((id) => ({ id, endpoint: byId.get(id) })),
    ...endpoints
      .filter((e) => !value.includes(e.id))
      .map((e) => ({ id: e.id, endpoint: e })),
  ];

  const toggle = (id: string, next: boolean) => {
    if (next) {
      if (!value.includes(id)) onChange([...value, id]);
    } else {
      onChange(value.filter((x) => x !== id));
    }
  };
  const move = (index: number, offset: -1 | 1) => {
    const nextIndex = index + offset;
    if (nextIndex < 0 || nextIndex >= value.length) return;
    const next = [...value];
    [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
    onChange(next);
  };

  const renderConfig = (
    endpoint: Endpoint | undefined,
    id: string,
    enabled: boolean,
  ) => (
    <span
      className={cn(
        "flex min-w-0 flex-col gap-2",
        !enabled && "opacity-60 transition-opacity",
      )}
    >
      <span className="block min-w-0 max-w-full truncate text-sm font-semibold leading-tight text-brand">
        {endpoint?.name ?? id}
      </span>
      <span className="block min-w-0 max-w-full truncate font-mono text-xs leading-snug text-ink-500">
        {endpoint?.url ?? "--"}
      </span>
      {endpoint ? (
        <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <span className="rounded-full bg-brand-soft px-2 py-0.5 text-2xs font-medium text-brand">
            {chainLabel(endpoint.chain as RpcChain)}
          </span>
          <span className="rounded-full bg-brand-soft px-2 py-0.5 text-2xs font-medium text-brand">
            {networkLabel(
              endpoint.chain as RpcChain,
              endpoint.network as RpcNetwork,
            )}
          </span>
        </span>
      ) : null}
    </span>
  );

  // Controls stay mounted for unassigned rows so the table keeps one column
  // rhythm; they read as disabled until the switch is on. Priority controls are
  // exclusive to priority failover because row order does not affect load
  // balancing.
  const weightControls = (id: string, name: string, enabled: boolean) => (
    <div className="flex items-center justify-end gap-2">
      <WeightRatioInput
        value={enabled ? weights?.[id] : undefined}
        onChange={(n) => onWeightChange?.(id, n)}
        disabled={disabled || !enabled}
        ariaLabel={t("weights.relativeInputLabel", { name })}
      />
      <WeightShare
        percent={
          enabled && isValidWeight(weights?.[id])
            ? normalizedShares[id]
            : undefined
        }
      />
    </div>
  );

  const priorityControls = (index: number, name: string, enabled: boolean) => (
    <div className="flex items-center justify-end gap-1">
      <span
        className={cn(
          "mr-1 flex size-7 items-center justify-center rounded-full bg-ink-wash text-xs font-semibold tabular-nums",
          enabled ? "text-ink-600" : "text-ink-400",
        )}
      >
        {enabled ? index + 1 : "--"}
      </span>
      <RowIconButton
        label={`${t("form.moveUp")} ${name}`}
        onClick={() => move(index, -1)}
        disabled={disabled || !enabled || index === 0}
      >
        <ArrowUpIcon className="size-3.5" aria-hidden />
      </RowIconButton>
      <RowIconButton
        label={`${t("form.moveDown")} ${name}`}
        onClick={() => move(index, 1)}
        disabled={disabled || !enabled || index === value.length - 1}
      >
        <ArrowDownIcon className="size-3.5" aria-hidden />
      </RowIconButton>
    </div>
  );

  const columns = 4;

  return (
    <div
      data-slot="endpoint-pool-table"
      className="overflow-hidden rounded-3xl bg-table-frame"
    >
      {/* Title mirrors GatewaySectionGroup's header, so the pool reads as a peer
       * of the other routing sub-groups rather than an untitled slab. */}
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
        <div className="min-w-0 flex-1 basis-52">
          <h3 className="text-sm font-semibold text-ink-900">{title}</h3>
          {description ? (
            <p className="mt-0.5 text-2xs leading-snug text-ink-500">
              {description}
            </p>
          ) : null}
        </div>
        <NewEndpointButton
          label={t("endpointTable.createEndpoint")}
          size="sm"
          variant="soft"
          showIcon={false}
          className="rounded-xl"
          disabled={disabled}
          initialChain={chain as Chain}
          initialNetwork={network as Network}
          initialProtocol={protocol}
          presentation="dialog"
        />
      </header>
      <div className="mx-1 mb-1 overflow-hidden rounded-table-pill bg-surface">
        <div className="overflow-x-auto">
          <table
            aria-label={t("form.endpoints")}
            className="w-full table-fixed border-collapse"
          >
            <colgroup>
              <col />
              {weighted ? <col className="w-48" /> : null}
              {!weighted ? <col className="w-32" /> : null}
              <col className="w-20" />
              <col className="w-20" />
            </colgroup>
            <thead className="border-b border-ink-wash">
              <tr>
                <th className="px-4 py-4 text-left text-sm font-semibold text-ink-900">
                  {t("endpointTable.configuration")}
                </th>
                {weighted ? (
                  <th className="px-4 py-4 text-right text-sm font-semibold text-ink-900">
                    {t("weights.relativeColumn")}
                  </th>
                ) : null}
                {!weighted ? (
                  <th className="px-4 py-4 text-right text-sm font-semibold text-ink-900">
                    {t("endpointTable.priority")}
                  </th>
                ) : null}
                <th className="px-4 py-4 text-right text-sm font-semibold text-ink-900">
                  {t("endpointTable.state")}
                </th>
                <th className="px-4 py-4 text-right text-sm font-semibold text-ink-900">
                  {t("endpointTable.actions")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-wash">
              {rows.length === 0 ? (
                <tr>
                  <td
                    colSpan={columns}
                    className="px-4 py-8 text-center text-sm text-ink-400"
                  >
                    {t("endpointTable.empty")}
                  </td>
                </tr>
              ) : (
                rows.map(({ id, endpoint }, index) => {
                  const name = endpoint?.name ?? id;
                  // Enabled rows lead the list, so the row index doubles as the
                  // pool position for the reorder controls.
                  const enabled = index < value.length;
                  return (
                    <tr key={id}>
                      <td className="min-w-0 px-4 py-4 align-top">
                        {renderConfig(endpoint, id, enabled)}
                      </td>
                      {weighted ? (
                        <td className="px-4 py-4 align-top">
                          {weightControls(id, name, enabled)}
                        </td>
                      ) : null}
                      {!weighted ? (
                        <td className="px-4 py-4 align-top">
                          {priorityControls(index, name, enabled)}
                        </td>
                      ) : null}
                      <td className="px-4 py-4 align-top">
                        <div className="flex justify-end">
                          <Switch
                            checked={enabled}
                            onCheckedChange={(next) => toggle(id, next)}
                            disabled={disabled}
                            aria-label={t("endpointTable.toggleLabel", {
                              name,
                            })}
                          />
                        </div>
                      </td>
                      <td className="px-4 py-4 align-top">
                        <div className="flex justify-end">
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon-xs"
                            className="text-ink-400 hover:text-destructive"
                            aria-label={t("endpointTable.deleteLabel", {
                              name,
                            })}
                            title={t("endpointTable.deleteLabel", { name })}
                            disabled={disabled || !endpoint}
                            onClick={() =>
                              endpoint && setDeleteTarget(endpoint)
                            }
                          >
                            <Trash2Icon aria-hidden />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
      <DeleteEndpointDialog
        endpoint={deleteTarget}
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        onDeleted={(id) => {
          if (value.includes(id)) {
            onChange(value.filter((item) => item !== id));
          }
        }}
      />
    </div>
  );
}

function RowIconButton({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      className="inline-flex size-6 shrink-0 items-center justify-center rounded-md text-ink-400 transition-colors hover:bg-surface hover:text-ink-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  );
}
