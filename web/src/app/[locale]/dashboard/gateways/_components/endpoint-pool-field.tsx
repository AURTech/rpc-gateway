"use client";

import { CircleHelpIcon, GripVerticalIcon, Trash2Icon } from "lucide-react";
import { Reorder, useDragControls } from "motion/react";
import { useTranslations } from "next-intl";
import { type ReactNode, useState } from "react";

import type { Endpoint, EndpointProtocol } from "@/api/endpoints/client";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useEndpointsQuery } from "@/hooks/use-endpoints";
import { useMotionPreset } from "@/hooks/use-motion-preset";
import type { Chain, Network } from "@/lib/blockchain";
import {
  type EndpointWeights,
  isValidWeight,
  sharePercents,
  weightsValid,
} from "@/lib/endpoint-weights";
import type { RpcChain, RpcNetwork } from "@/lib/rpc-chain";
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
 * The default grouped presentation includes a compact header and create action.
 * The embedded presentation omits that header so a parent configuration group
 * can own the title, description, and action without duplicating hierarchy.
 * Both presentations wrap one table listing EVERY endpoint for this
 * chain/network. A per-row switch turns an endpoint on for this gateway, so
 * assigning and unassigning happen in place — no tab to switch back to. Enabled
 * rows sort above the rest in pool order; disabled rows keep their controls
 * visible but inert. When `weighted` is on, an extra column exposes each row's
 * raw weight input (1–1000, the API `weight`) plus a read-only % share preview.
 *
 * Endpoints come from the account-global registry, filtered to this gateway's
 * chain/network and the route protocol selected by the caller.
 */
export function EndpointPoolField({
  chain,
  network,
  protocol = "jsonrpc",
  embedded = false,
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
  /** Omits this component's heading and create action inside a parent group. */
  embedded?: boolean;
  /** Sub-group heading — the pool serves both the default route and rules. */
  title?: string;
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
        "flex min-w-0 flex-1 flex-col gap-1",
        !enabled && "opacity-60 transition-opacity",
      )}
    >
      <span className="block min-w-0 max-w-full truncate text-sm font-semibold leading-tight text-brand">
        {endpoint?.name ?? id}
      </span>
      <span className="block min-w-0 max-w-full truncate font-mono text-xs leading-snug text-ink-500">
        {endpoint?.url ?? "--"}
      </span>
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

  const priorityControls = (
    index: number,
    enabled: boolean,
    dragHandle: ReactNode,
  ) => (
    <span className="flex shrink-0 items-center gap-0.5">
      {dragHandle ?? (
        <span
          aria-hidden
          className="flex size-7 items-center justify-center text-ink-300"
        >
          <GripVerticalIcon className="size-4" />
        </span>
      )}
      <span
        className={cn(
          "flex h-7 w-5 items-center justify-center text-xs font-semibold tabular-nums",
          enabled ? "text-ink-600" : "text-ink-400",
        )}
      >
        {enabled ? index + 1 : "--"}
      </span>
    </span>
  );

  const columns = weighted ? 4 : 3;

  const renderRows = (sortable: boolean) => {
    if (rows.length === 0) {
      return (
        <tr>
          <td colSpan={columns} className="px-4 py-10 text-center">
            <div className="flex flex-col items-center gap-3">
              <div className="flex max-w-md flex-col gap-1">
                <p className="text-sm font-semibold text-ink-700">
                  {t("endpointTable.emptyTitle")}
                </p>
                <p className="text-sm text-ink-500">
                  {t("endpointTable.emptyDescription")}
                </p>
              </div>
              <NewEndpointButton
                label={t("endpointTable.createEndpoint")}
                size="sm"
                variant="soft"
                className="rounded-xl"
                disabled={disabled}
                initialChain={chain as Chain}
                initialNetwork={network as Network}
                initialProtocol={protocol}
                presentation="dialog"
              />
            </div>
          </td>
        </tr>
      );
    }

    return rows.map(({ id, endpoint }, index) => {
      const name = endpoint?.name ?? id;
      // Enabled rows lead the list, so the row index doubles as the pool
      // position used by drag-and-drop and keyboard reordering.
      const enabled = index < value.length;
      const cells = (dragHandle: ReactNode) => (
        <>
          <td className="min-w-0 px-4 py-3 align-middle">
            <div className="flex min-w-0 items-start gap-2">
              {!weighted ? priorityControls(index, enabled, dragHandle) : null}
              {renderConfig(endpoint, id, enabled)}
            </div>
          </td>
          {weighted ? (
            <td className="px-4 py-3 align-middle">
              {weightControls(id, name, enabled)}
            </td>
          ) : null}
          <td className="px-4 py-3 align-middle">
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
          <td className="px-4 py-3 align-middle">
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
                onClick={() => endpoint && setDeleteTarget(endpoint)}
              >
                <Trash2Icon aria-hidden />
              </Button>
            </div>
          </td>
        </>
      );

      return sortable && enabled ? (
        <PriorityEndpointRow
          key={id}
          id={id}
          disabled={disabled}
          reorderLabel={t("endpointTable.reorderLabel", {
            name,
            priority: index + 1,
          })}
          onMove={(offset) => move(index, offset)}
        >
          {cells}
        </PriorityEndpointRow>
      ) : (
        <tr key={id}>{cells(null)}</tr>
      );
    });
  };

  return (
    <div
      data-slot="endpoint-pool-table"
      className={cn(
        "overflow-hidden bg-table-frame",
        embedded ? "rounded-table-pill p-1" : "rounded-3xl",
      )}
    >
      {!embedded ? (
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
      ) : null}
      <div
        className={cn(
          "overflow-hidden rounded-table-pill bg-surface",
          !embedded && "mx-1 mb-1",
        )}
      >
        <div className="overflow-x-auto">
          <table
            aria-label={t("form.endpoints")}
            className="w-full table-fixed border-collapse"
          >
            <colgroup>
              <col />
              {weighted ? <col className="w-40" /> : null}
              <col className="w-20" />
              <col className="w-20" />
            </colgroup>
            <thead className="border-b border-ink-wash">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-ink-500">
                  {t("endpointTable.configuration")}
                </th>
                {weighted ? (
                  <th className="px-4 py-3 text-right text-xs font-medium text-ink-500">
                    <WeightHeaderLabel
                      label={t("weights.relativeColumn")}
                      hint={t("weights.relativeHint")}
                    />
                  </th>
                ) : null}
                <th className="px-4 py-3 text-right text-xs font-medium text-ink-500">
                  {t("endpointTable.state")}
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-ink-500">
                  {t("endpointTable.actions")}
                </th>
              </tr>
            </thead>
            {!weighted ? (
              <Reorder.Group
                as="tbody"
                axis="y"
                values={value}
                onReorder={(next) => {
                  if (!disabled) onChange(next);
                }}
                className="divide-y divide-ink-wash"
              >
                {renderRows(true)}
              </Reorder.Group>
            ) : (
              <tbody className="divide-y divide-ink-wash">
                {renderRows(false)}
              </tbody>
            )}
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

function PriorityEndpointRow({
  id,
  disabled,
  reorderLabel,
  onMove,
  children,
}: {
  id: string;
  disabled?: boolean;
  reorderLabel: string;
  onMove: (offset: -1 | 1) => void;
  children: (dragHandle: ReactNode) => ReactNode;
}) {
  const dragControls = useDragControls();
  const motionPreset = useMotionPreset();

  const dragHandle = (
    <button
      type="button"
      aria-label={reorderLabel}
      title={reorderLabel}
      disabled={disabled}
      onPointerDown={(event) => dragControls.start(event)}
      onKeyDown={(event) => {
        if (event.key === "ArrowUp") {
          event.preventDefault();
          onMove(-1);
        } else if (event.key === "ArrowDown") {
          event.preventDefault();
          onMove(1);
        }
      }}
      className="inline-flex size-7 shrink-0 touch-none cursor-grab items-center justify-center rounded-md text-ink-400 transition-colors hover:bg-ink-wash hover:text-ink-700 active:cursor-grabbing focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 disabled:cursor-not-allowed disabled:opacity-40"
    >
      <GripVerticalIcon className="size-4" aria-hidden />
    </button>
  );

  return (
    <Reorder.Item
      as="tr"
      value={id}
      dragListener={false}
      dragControls={dragControls}
      whileDrag={{ opacity: 0.72 }}
      transition={motionPreset.transition({
        duration: 0.15,
        ease: "easeOut",
      })}
      className="relative bg-surface"
    >
      {children(dragHandle)}
    </Reorder.Item>
  );
}

function WeightHeaderLabel({ label, hint }: { label: string; hint: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="ml-auto flex items-center gap-1 rounded-md text-xs font-medium text-ink-500 outline-none transition-colors hover:text-ink-700 focus-visible:ring-2 focus-visible:ring-brand/40"
        >
          {label}
          <CircleHelpIcon className="size-3.5" aria-hidden />
        </button>
      </TooltipTrigger>
      <TooltipContent side="top">{hint}</TooltipContent>
    </Tooltip>
  );
}
