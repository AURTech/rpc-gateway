"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import type {
  RpcProviderSyncAction,
  RpcProviderSyncResult,
  RpcProviderSyncStatus,
} from "@/api/providers/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { networkLabel, type RpcChain } from "@/lib/rpc-chain";
import { cn } from "@/lib/utils";

const STATUS_VARIANTS: Record<
  RpcProviderSyncStatus,
  React.ComponentProps<typeof Badge>["variant"]
> = {
  never: "neutral",
  success: "positive",
  partial: "warning",
  failed: "danger",
};

const ACTION_VARIANTS: Record<
  RpcProviderSyncAction,
  React.ComponentProps<typeof Badge>["variant"]
> = {
  created: "positive",
  updated: "brand",
  restored: "positive",
  archived: "neutral",
  skipped: "neutral",
  failed: "danger",
};

export function SyncResultDialog({
  providerName,
  result,
  open,
  onOpenChange,
}: {
  providerName: string;
  result: RpcProviderSyncResult | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("dashboard.providers");
  const [showItems, setShowItems] = useState(false);

  if (!result) return null;

  const stats: { key: string; label: string; value: number }[] = [
    { key: "created", label: t("sync.created"), value: result.created },
    { key: "updated", label: t("sync.updated"), value: result.updated },
    { key: "restored", label: t("sync.restored"), value: result.restored },
    { key: "archived", label: t("sync.archived"), value: result.archived },
    { key: "skipped", label: t("sync.skipped"), value: result.skipped },
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="gap-5 sm:max-w-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 pr-8 text-xl font-bold tracking-tight">
            {t("sync.title")}
            <Badge variant={STATUS_VARIANTS[result.status]} dot>
              {result.status_label}
            </Badge>
          </DialogTitle>
          <DialogDescription>
            {t("sync.subtitle", { name: providerName })}
          </DialogDescription>
        </DialogHeader>

        {result.status !== "never" ? (
          <p className="text-md text-ink-700">
            {t(`sync.summary.${result.status}`)}
          </p>
        ) : null}

        <dl className="grid grid-cols-5 gap-2">
          {stats.map((stat) => (
            <div
              key={stat.key}
              className="flex flex-col gap-1 rounded-xl bg-ink-wash px-3 py-2.5"
            >
              <dt className="text-sm text-ink-500">{stat.label}</dt>
              <dd className="text-lg font-bold tabular-nums text-ink-900">
                {stat.value}
              </dd>
            </div>
          ))}
        </dl>

        {result.items.length > 0 ? (
          <div className="flex flex-col gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="self-start"
              onClick={() => setShowItems((v) => !v)}
            >
              {showItems ? t("sync.hideItems") : t("sync.viewItems")}
            </Button>
            {showItems ? (
              <div className="max-h-64 overflow-y-auto rounded-xl border border-table-frame">
                <table className="w-full text-left text-sm">
                  <thead className="sticky top-0 bg-surface">
                    <tr className="text-ink-500">
                      <th className="px-3 py-2 font-medium">
                        {t("sync.colChain")}
                      </th>
                      <th className="px-3 py-2 font-medium">
                        {t("sync.colNetwork")}
                      </th>
                      <th className="px-3 py-2 font-medium">
                        {t("sync.colAction")}
                      </th>
                      <th className="px-3 py-2 font-medium">
                        {t("sync.colError")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.items.map((item, i) => (
                      <tr
                        key={`${item.external_id ?? item.endpoint_id ?? i}`}
                        className={cn(
                          "border-table-frame border-t",
                          item.action === "failed" && "bg-danger-soft",
                        )}
                      >
                        <td className="px-3 py-2 text-ink-700">
                          {item.chain ?? "—"}
                        </td>
                        <td className="px-3 py-2 text-ink-700">
                          {item.chain && item.network
                            ? networkLabel(item.chain as RpcChain, item.network)
                            : (item.network ?? "—")}
                        </td>
                        <td className="px-3 py-2">
                          <Badge variant={ACTION_VARIANTS[item.action]}>
                            {item.action_label}
                          </Badge>
                        </td>
                        <td className="px-3 py-2 text-danger">
                          {item.error ?? ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-ink-500">
            {result.status === "success"
              ? t("sync.upToDate")
              : t("sync.noItems")}
          </p>
        )}

        <DialogFooter>
          <Button type="button" onClick={() => onOpenChange(false)}>
            {t("sync.close")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
