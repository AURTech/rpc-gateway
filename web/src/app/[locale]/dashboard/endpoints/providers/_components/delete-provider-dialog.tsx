"use client";

import { LoaderCircleIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import type { RpcProvider } from "@/api/providers/client";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import { useDeleteProvider, useProviderDeleteImpact } from "./use-providers";

type DeleteStrategy = "detach" | "cleanup";

function DeleteProviderContent({
  provider,
  open,
  onOpenChange,
  onRemoved,
}: {
  provider: RpcProvider;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRemoved: (id: string) => void;
}) {
  const t = useTranslations("dashboard.endpointProviders.delete");
  const remove = useDeleteProvider(provider.id);
  const impact = useProviderDeleteImpact(provider.id, open);
  const [strategy, setStrategy] = useState<DeleteStrategy>("detach");
  const managedCount = impact.data?.managed_endpoints ?? 0;

  async function confirmDelete() {
    await remove.mutateAsync({
      delete_unreferenced_endpoints: strategy === "cleanup",
    });
    onRemoved(provider.id);
  }

  return (
    <DialogContent closeLabel={t("close")}>
      <DialogHeader>
        <DialogTitle>{t("title", { name: provider.name })}</DialogTitle>
        <DialogDescription>
          {t("impact", { count: managedCount })}
        </DialogDescription>
      </DialogHeader>
      {impact.isLoading ? (
        <Skeleton className="h-24 w-full rounded-lg" />
      ) : impact.isError ? (
        <div className="rounded-lg bg-danger-soft p-4 text-sm text-danger">
          <p>{t("impactError")}</p>
          <Button
            className="mt-3"
            size="sm"
            variant="soft"
            onClick={() => impact.refetch()}
          >
            {t("retryImpact")}
          </Button>
        </div>
      ) : impact.data ? (
        <dl className="grid grid-cols-3 gap-2 rounded-lg bg-ink-wash p-4 text-sm">
          <div>
            <dt className="text-ink-500">{t("apps")}</dt>
            <dd className="mt-1 font-semibold tabular-nums text-ink-900">
              {impact.data.connected_apps}
            </dd>
          </div>
          <div>
            <dt className="text-ink-500">{t("routeTargets")}</dt>
            <dd className="mt-1 font-semibold tabular-nums text-ink-900">
              {impact.data.automatic_route_targets}
            </dd>
          </div>
          <div>
            <dt className="text-ink-500">{t("managedEndpoints")}</dt>
            <dd className="mt-1 font-semibold tabular-nums text-ink-900">
              {impact.data.managed_endpoints}
            </dd>
          </div>
          <div>
            <dt className="text-ink-500">{t("wouldDetach")}</dt>
            <dd className="mt-1 font-semibold tabular-nums text-ink-900">
              {impact.data.would_detach}
            </dd>
          </div>
          <div>
            <dt className="text-ink-500">{t("wouldArchive")}</dt>
            <dd className="mt-1 font-semibold tabular-nums text-ink-900">
              {impact.data.would_archive}
            </dd>
          </div>
          <div>
            <dt className="text-ink-500">{t("wouldRetain")}</dt>
            <dd className="mt-1 font-semibold tabular-nums text-ink-900">
              {impact.data.would_retain}
            </dd>
          </div>
        </dl>
      ) : null}
      <div className="space-y-3">
        {(["detach", "cleanup"] as const).map((value) => (
          <label
            key={value}
            htmlFor={`delete-provider-strategy-${value}`}
            className={cn(
              "block w-full cursor-pointer rounded-lg bg-ink-wash p-4 text-left outline-none hover:bg-stripe focus-within:ring-2 focus-within:ring-brand/40",
              strategy === value && "bg-brand-soft ring-2 ring-brand/30",
            )}
          >
            <input
              id={`delete-provider-strategy-${value}`}
              type="radio"
              name="delete-provider-strategy"
              value={value}
              checked={strategy === value}
              onChange={() => setStrategy(value)}
              className="sr-only"
            />
            <span className="block font-semibold text-ink-900">
              {t(`strategy.${value}.title`)}
            </span>
            <span className="mt-1 block text-sm text-ink-500">
              {t(`strategy.${value}.body`)}
            </span>
          </label>
        ))}
      </div>
      {remove.isError ? (
        <p role="alert" className="text-sm text-danger">
          {remove.error.message}
        </p>
      ) : null}
      <DialogFooter>
        <Button variant="ghost" onClick={() => onOpenChange(false)}>
          {t("cancel")}
        </Button>
        <Button
          variant="destructive"
          disabled={remove.isPending || impact.isLoading || impact.isError}
          onClick={confirmDelete}
        >
          {remove.isPending ? (
            <LoaderCircleIcon className="animate-spin" />
          ) : null}
          {t("confirm")}
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}

function DeleteProviderDialog({
  provider,
  open,
  onOpenChange,
  onRemoved,
}: {
  provider: RpcProvider | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRemoved: (id: string) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {provider ? (
        <DeleteProviderContent
          key={provider.version}
          provider={provider}
          open={open}
          onOpenChange={onOpenChange}
          onRemoved={onRemoved}
        />
      ) : null}
    </Dialog>
  );
}

export { DeleteProviderDialog };
