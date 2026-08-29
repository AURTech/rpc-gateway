"use client";

import {
  AlertTriangle,
  CheckCircle2,
  LoaderCircle,
  RefreshCw,
} from "lucide-react";
import { useTranslations } from "next-intl";

import type { RpcProviderSyncRun } from "@/api/providers/client";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type SyncDialogState =
  | "starting"
  | "queued"
  | "running"
  | "success"
  | "partial"
  | "failed";

interface ProviderSyncDialogProps {
  providerName: string;
  open: boolean;
  run: RpcProviderSyncRun | null;
  starting: boolean;
  startError: string | null;
  statusError: boolean;
  onOpenChange: (open: boolean) => void;
  onRetryStart: () => void;
  onRetryStatus: () => void;
}

function runState(
  run: RpcProviderSyncRun | null,
  starting: boolean,
  startError: string | null,
): SyncDialogState {
  if (startError) return "failed";
  if (starting || !run) return "starting";
  return run.state;
}

export function ProviderSyncDialog({
  providerName,
  open,
  run,
  starting,
  startError,
  statusError,
  onOpenChange,
  onRetryStart,
  onRetryStatus,
}: ProviderSyncDialogProps) {
  const t = useTranslations("dashboard.endpointProviders.syncDialog");
  const state = runState(run, starting, startError);
  const working =
    state === "starting" || state === "queued" || state === "running";
  const failed = state === "failed";
  const partial = state === "partial";
  const changes = run?.endpoint_changes ?? 0;
  const body = statusError
    ? t("statusError")
    : failed
      ? run?.error || startError || t("failedBody")
      : partial
        ? t("partialBody", { count: changes })
        : state === "success"
          ? changes > 0
            ? t("changes", { count: changes })
            : t("noChanges")
          : t("workingBody");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" closeLabel={t("close")}>
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>{providerName}</DialogDescription>
        </DialogHeader>

        <output
          aria-live="polite"
          className="flex items-start gap-3 rounded-lg bg-ink-wash p-4"
        >
          {working ? (
            <LoaderCircle
              className="mt-0.5 size-5 shrink-0 animate-spin text-brand"
              aria-hidden
            />
          ) : failed || partial ? (
            <AlertTriangle
              className={`mt-0.5 size-5 shrink-0 ${failed ? "text-danger" : "text-warning"}`}
              aria-hidden
            />
          ) : (
            <CheckCircle2
              className="mt-0.5 size-5 shrink-0 text-positive"
              aria-hidden
            />
          )}
          <div className="min-w-0">
            <p className="font-semibold text-ink-900">{t(`state.${state}`)}</p>
            <p className="mt-1 text-sm text-ink-500">{body}</p>
          </div>
        </output>

        <DialogFooter>
          {startError ? (
            <Button variant="soft" onClick={onRetryStart}>
              <RefreshCw aria-hidden />
              {t("retry")}
            </Button>
          ) : statusError ? (
            <Button variant="soft" onClick={onRetryStatus}>
              <RefreshCw aria-hidden />
              {t("retry")}
            </Button>
          ) : null}
          <Button
            variant={working ? "ghost" : "default"}
            onClick={() => onOpenChange(false)}
          >
            {working ? t("close") : t("done")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
