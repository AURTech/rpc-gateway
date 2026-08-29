"use client";

import { BookOpenIcon, CheckIcon, CopyIcon, PencilIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { isApiError } from "@/api/client";
import type {
  RpcGatewayDetail,
  RpcGatewayTransport,
} from "@/api/gateways/client";
import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { Button } from "@/components/ui/button";
import { ChainIcon } from "@/components/ui/chain-icon";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import type { GatewayPathKeyStatus } from "@/hooks/use-gateway-path-key";
import { useUpdateGatewayMutation } from "@/hooks/use-gateways";
import { copyToClipboard } from "@/lib/clipboard";
import { chainLabel, networkLabel } from "@/lib/rpc-chain";
import { fillPathKeyTemplate } from "@/lib/rpc-endpoint";
import { cn } from "@/lib/utils";

import { IconButton } from "../../_components/compact-drawer";

const NAME_MAX = 128;

/**
 * Gateway page header with identity, effective traffic state, and its own
 * enable switch. App-level disablement can make an enabled Gateway ineffective.
 */
export function GatewayHeader({
  gateway,
  transport,
  pathKey,
  pathKeyStatus,
}: {
  gateway: RpcGatewayDetail;
  transport: RpcGatewayTransport;
  pathKey: string | null;
  pathKeyStatus: GatewayPathKeyStatus;
}) {
  const t = useTranslations("dashboard.gateways");
  const update = useUpdateGatewayMutation();

  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(gateway.name);
  const [pendingEnabled, setPendingEnabled] = useState<boolean | null>(null);
  const [copiedUrl, setCopiedUrl] = useState<string | null>(null);
  const copiedResetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const trimmedName = name.trim();
  const nameValid = trimmedName.length > 0 && trimmedName.length <= NAME_MAX;
  const nameDirty = nameValid && trimmedName !== gateway.name;
  const accessPoint = gateway.access_points.find(
    (point) => point.transport === transport,
  );
  const accessPointUrl =
    accessPoint && pathKey
      ? fillPathKeyTemplate(accessPoint.url, pathKey)
      : accessPoint?.url;
  const transportLabel = t(
    `apiTypes.${transport === "http_api" ? "httpapi" : transport}`,
  );

  useEffect(
    () => () => {
      if (copiedResetTimer.current) clearTimeout(copiedResetTimer.current);
    },
    [],
  );

  const startEdit = () => {
    setName(gateway.name);
    setEditing(true);
  };

  const cancelEdit = () => {
    setName(gateway.name);
    setEditing(false);
  };

  const saveName = () => {
    if (!nameDirty) {
      cancelEdit();
      return;
    }
    update.mutate(
      {
        id: gateway.id,
        input: { name: trimmedName, expected_version: gateway.version },
      },
      {
        onSuccess: () => {
          toast.success(t("toast.updated"));
          setEditing(false);
        },
        onError: (err) =>
          toast.error(
            isApiError(err) && err.message
              ? err.message
              : t("toast.updateError"),
          ),
      },
    );
  };

  const toggleEnabled = (enabled: boolean) => {
    update.mutate(
      {
        id: gateway.id,
        input: { enabled, expected_version: gateway.version },
      },
      {
        onSuccess: () => {
          toast.success(t(enabled ? "toast.enabled" : "toast.disabled"));
          setPendingEnabled(null);
        },
        onError: (err) =>
          toast.error(
            isApiError(err) && err.message
              ? err.message
              : t("toast.updateError"),
          ),
      },
    );
  };

  const copyAccessPoint = async (url: string) => {
    const copied = await copyToClipboard(url);
    if (!copied) {
      toast.error(t("toast.copyError"));
      return;
    }
    setCopiedUrl(url);
    toast.success(t("toast.copyOk"));
    if (copiedResetTimer.current) clearTimeout(copiedResetTimer.current);
    copiedResetTimer.current = setTimeout(() => setCopiedUrl(null), 1800);
  };

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div className="flex min-w-0 flex-1 basis-72 items-center gap-3">
          <ChainIcon
            chain={gateway.chain}
            network={gateway.network}
            className="size-8 shrink-0"
          />
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            {editing ? (
              <div className="flex flex-wrap items-center gap-2">
                <Input
                  autoFocus
                  type="text"
                  autoComplete="off"
                  maxLength={NAME_MAX}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={update.isPending}
                  aria-label={t("form.name")}
                  className="h-9 max-w-xs text-md font-semibold"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") saveName();
                    if (e.key === "Escape") cancelEdit();
                  }}
                />
                <Button
                  type="button"
                  size="sm"
                  onClick={saveName}
                  disabled={!nameDirty || update.isPending}
                >
                  {update.isPending ? t("dialog.saving") : t("dialog.save")}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={cancelEdit}
                  disabled={update.isPending}
                >
                  {t("dialog.cancel")}
                </Button>
              </div>
            ) : (
              <div className="flex min-w-0 items-center gap-2">
                <p className="min-w-0 truncate text-xl font-bold tracking-tight text-ink-900">
                  {gateway.name}
                </p>
                <IconButton
                  ariaLabel={t("actions.rename")}
                  onClick={startEdit}
                  className="size-7"
                >
                  <PencilIcon className="size-3.5" aria-hidden />
                </IconButton>
              </div>
            )}
            <div className="flex flex-wrap items-center gap-x-1.5 text-xs text-ink-500">
              <span>{chainLabel(gateway.chain)}</span>
              <span aria-hidden>·</span>
              <span>{networkLabel(gateway.chain, gateway.network)}</span>
              <span aria-hidden>·</span>
              <span>{transportLabel}</span>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2 sm:shrink-0">
          <a
            href="https://rpc.aurpay.net"
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2 text-sm font-medium text-brand transition-colors hover:bg-brand-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
          >
            <BookOpenIcon className="size-4" aria-hidden />
            {t("cta.viewDocs")}
          </a>
          <span
            className={cn(
              "text-sm font-medium",
              gateway.effective_enabled ? "text-positive" : "text-ink-500",
            )}
          >
            {gateway.enabled
              ? gateway.effective_enabled
                ? t("form.trafficOn")
                : t("form.trafficBlockedByApp")
              : t("form.trafficOff")}
          </span>
          <Switch
            checked={gateway.enabled}
            onCheckedChange={(enabled) => {
              if (enabled !== gateway.enabled) setPendingEnabled(enabled);
            }}
            disabled={update.isPending}
            aria-label={t("form.enabledEdit")}
          />
        </div>
      </div>

      {accessPoint && pathKeyStatus === "metadata-loading" ? (
        <Skeleton className="h-11 w-full rounded-xl" />
      ) : accessPointUrl ? (
        <div className="flex min-w-0 items-center gap-2 rounded-xl bg-ink-wash p-1.5 pl-3">
          <div className="min-w-0 flex-1">
            <span className="sr-only">{transportLabel}</span>
            <code className="block break-all whitespace-normal font-mono text-sm text-ink-700">
              {accessPointUrl}
            </code>
          </div>
          <Button
            type="button"
            size="icon-sm"
            variant="soft"
            className="rounded-lg"
            aria-label={t("table.copyEndpoint", { name: transportLabel })}
            onClick={() => copyAccessPoint(accessPointUrl)}
          >
            {copiedUrl === accessPointUrl ? (
              <CheckIcon aria-hidden />
            ) : (
              <CopyIcon aria-hidden />
            )}
          </Button>
        </div>
      ) : null}

      <ConfirmDialog
        open={pendingEnabled !== null}
        onOpenChange={(next) => {
          if (!update.isPending && !next) setPendingEnabled(null);
        }}
        title={
          pendingEnabled
            ? t("dialog.status.enable.title")
            : t("dialog.status.disable.title")
        }
        description={
          pendingEnabled
            ? t("dialog.status.enable.body", { name: gateway.name })
            : t("dialog.status.disable.body", { name: gateway.name })
        }
        onConfirm={() => {
          if (pendingEnabled !== null) toggleEnabled(pendingEnabled);
        }}
        confirmLabel={
          pendingEnabled
            ? t("dialog.status.enable.confirm")
            : t("dialog.status.disable.confirm")
        }
        confirmingLabel={t("dialog.saving")}
        cancelLabel={t("dialog.cancel")}
        confirming={update.isPending}
        destructive={pendingEnabled === false}
        contentClassName="sm:max-w-dialog"
      />
    </section>
  );
}
