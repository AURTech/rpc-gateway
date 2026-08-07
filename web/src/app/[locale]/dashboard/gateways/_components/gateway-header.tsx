"use client";

import { ChevronLeftIcon, PencilIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { isApiError } from "@/api/client";
import type { RpcGatewayDetail } from "@/api/gateways/client";
import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { Button } from "@/components/ui/button";
import { ChainIcon } from "@/components/ui/chain-icon";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useUpdateGatewayMutation } from "@/hooks/use-gateways";
import { Link } from "@/i18n/navigation";
import { chainLabel, networkLabel } from "@/lib/rpc-chain";
import { cn } from "@/lib/utils";

import { IconButton } from "../../_components/compact-drawer";

const NAME_MAX = 128;

/**
 * Gateway page header with identity, effective traffic state, and its own
 * enable switch. App-level disablement can make an enabled Gateway ineffective.
 */
export function GatewayHeader({
  gateway,
  backHref,
}: {
  gateway: RpcGatewayDetail;
  backHref: string;
}) {
  const t = useTranslations("dashboard.gateways");
  const update = useUpdateGatewayMutation();

  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(gateway.name);
  const [pendingEnabled, setPendingEnabled] = useState<boolean | null>(null);

  const trimmedName = name.trim();
  const nameValid = trimmedName.length > 0 && trimmedName.length <= NAME_MAX;
  const nameDirty = nameValid && trimmedName !== gateway.name;

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

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4">
        <div className="flex min-w-0 flex-1 basis-72 flex-col gap-2">
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
                className="h-10 max-w-xs text-lg font-semibold"
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
              <Link
                href={backHref}
                aria-label={t("page.back")}
                title={t("page.back")}
                className="-ml-1.5 inline-flex size-8 shrink-0 items-center justify-center rounded-md text-ink-400 transition-colors hover:bg-ink-wash hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
              >
                <ChevronLeftIcon className="size-5" aria-hidden />
              </Link>
              <ChainIcon
                chain={gateway.chain}
                network={gateway.network}
                className="size-6 shrink-0"
              />
              <h1 className="min-w-0 truncate text-2xl font-bold tracking-tight text-ink-900">
                {gateway.name}
              </h1>
              <IconButton
                ariaLabel={t("actions.rename")}
                onClick={startEdit}
                className="size-8"
              >
                <PencilIcon className="size-4" aria-hidden />
              </IconButton>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-500">
            <span>{chainLabel(gateway.chain)}</span>
            <span aria-hidden>·</span>
            <span>{networkLabel(gateway.chain, gateway.network)}</span>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-3">
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
    </div>
  );
}
