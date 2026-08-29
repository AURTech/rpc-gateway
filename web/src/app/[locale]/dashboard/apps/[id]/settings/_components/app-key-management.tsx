"use client";

import {
  CalendarClockIcon,
  CopyIcon,
  RotateCwIcon,
  ShieldOffIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import type { RpcAppKey, RpcAppKeyState } from "@/api/apps/client";
import { isApiError } from "@/api/client";
import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Time } from "@/components/ui/time";
import {
  useAppKeysQuery,
  useRevokeAppKeyMutation,
  useRotateAppKeyMutation,
} from "@/hooks/use-apps";
import { copyToClipboard } from "@/lib/clipboard";

const STATE_VARIANT: Record<
  RpcAppKeyState,
  "danger" | "neutral" | "positive" | "warning"
> = {
  active: "positive",
  grace: "warning",
  revoked: "danger",
  expired: "neutral",
};

function apiErrorMessage(error: unknown, fallback: string): string {
  return isApiError(error) && error.message ? error.message : fallback;
}

function shortResourceId(id: string): string {
  return id.length <= 12 ? id : `${id.slice(0, 8)}…${id.slice(-4)}`;
}

function KeyListSkeleton() {
  return ["first", "second"].map((key) => (
    <TableRow key={key} aria-hidden>
      <TableCell>
        <Skeleton className="h-5 w-full max-w-md" />
      </TableCell>
      <TableCell>
        <Skeleton className="h-5 w-16" />
      </TableCell>
      <TableCell>
        <Skeleton className="h-5 w-28" />
      </TableCell>
      <TableCell align="right">
        <Skeleton className="ml-auto h-8 w-24" />
      </TableCell>
    </TableRow>
  ));
}

export function AppKeyManagement({ appId }: { appId: string }) {
  const t = useTranslations("dashboard.apps.settings.keys");
  const ta = useTranslations("dashboard.apps");
  const query = useAppKeysQuery(appId);
  const rotateMutation = useRotateAppKeyMutation();
  const revokeMutation = useRevokeAppKeyMutation();

  const [rotateOpen, setRotateOpen] = useState(false);
  const [revokeKey, setRevokeKey] = useState<RpcAppKey | null>(null);

  const rotate = () => {
    rotateMutation.mutate(appId, {
      onSuccess: () => {
        setRotateOpen(false);
        toast.success(t("toast.rotated"));
      },
      onError: (error) =>
        toast.error(apiErrorMessage(error, t("toast.rotateError"))),
    });
  };

  const copyKey = async (apiKey: string) => {
    const ok = await copyToClipboard(apiKey);
    if (ok) toast.success(ta("toast.copyOk"));
    else toast.error(ta("toast.copyError"));
  };

  const revoke = () => {
    if (!revokeKey) return;
    revokeMutation.mutate(
      { appId, keyId: revokeKey.id },
      {
        onSuccess: () => {
          toast.success(t("toast.revoked"));
          setRevokeKey(null);
        },
        onError: (error) =>
          toast.error(apiErrorMessage(error, t("toast.revokeError"))),
      },
    );
  };

  return (
    <>
      <div className="flex w-full flex-col gap-7">
        <header className="flex flex-col gap-1.5">
          <h1 className="text-3xl font-bold tracking-tight text-ink-900">
            {t("title")}
          </h1>
          <p className="max-w-prose-narrow text-md text-ink-600">
            {t("subtitle")}
          </p>
        </header>

        <section data-slot="app-key-management">
          <Table
            compact
            dividers
            aria-label={t("title")}
            className="min-w-176 table-fixed"
            containerClassName="shadow-section"
          >
            <TableCaption>{t("title")}</TableCaption>
            <colgroup>
              <col />
              <col className="w-32" />
              <col className="w-44" />
              <col className="w-32" />
            </colgroup>
            <TableHeader>
              <TableRow>
                <TableHead>{t("columns.apiKey")}</TableHead>
                <TableHead>{t("columns.state")}</TableHead>
                <TableHead>{t("columns.createdAt")}</TableHead>
                <TableHead align="right">{t("columns.actions")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.isPending ? <KeyListSkeleton /> : null}

              {query.isError ? (
                <TableRow>
                  <TableCell colSpan={4} className="h-36">
                    <div role="alert" className="mx-auto max-w-md text-center">
                      <p className="font-medium text-danger">
                        {t("error.title")}
                      </p>
                      <p className="mt-1 text-sm text-danger">
                        {t("error.body")}
                      </p>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => query.refetch()}
                        className="mt-3"
                      >
                        {t("error.retry")}
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ) : null}

              {query.data && query.data.items.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={4}
                    className="h-36 text-center text-ink-500"
                  >
                    {t("empty")}
                  </TableCell>
                </TableRow>
              ) : null}

              {query.data?.items.map((key) => {
                return (
                  <TableRow key={key.id}>
                    <TableCell className="min-w-0 overflow-hidden py-3 align-middle">
                      <div className="flex min-w-0 items-center gap-2">
                        <code
                          className="min-w-0 flex-1 truncate whitespace-nowrap font-mono text-xs leading-5 text-ink-700"
                          title={key.api_key}
                        >
                          {key.api_key}
                        </code>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          aria-label={t("copy")}
                          title={t("copy")}
                          onClick={() => copyKey(key.api_key)}
                          className="shrink-0"
                        >
                          <CopyIcon className="size-3.5" aria-hidden />
                        </Button>
                      </div>
                    </TableCell>
                    <TableCell className="py-3 align-middle">
                      <Badge
                        variant={STATE_VARIANT[key.state]}
                        className="text-ink-700"
                      >
                        {t(`states.${key.state}`)}
                      </Badge>
                    </TableCell>
                    <TableCell className="whitespace-nowrap py-3 align-middle">
                      <div className="inline-flex items-center gap-1.5 rounded-md bg-ink-wash px-2 py-1 text-ink-500">
                        <CalendarClockIcon
                          className="size-3.5 shrink-0"
                          aria-hidden
                        />
                        <Time
                          value={key.created_at}
                          className="font-mono text-xs font-medium tracking-tight text-ink-700"
                        />
                      </div>
                    </TableCell>
                    <TableCell align="right" className="py-3 align-middle">
                      {key.state === "active" ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => setRotateOpen(true)}
                          disabled={rotateMutation.isPending}
                          className="text-danger hover:bg-danger-soft hover:text-danger"
                        >
                          <RotateCwIcon className="size-3.5" aria-hidden />
                          {t("rotate")}
                        </Button>
                      ) : null}
                      {key.state === "grace" ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => setRevokeKey(key)}
                          disabled={revokeMutation.isPending}
                          className="text-danger hover:bg-danger-soft hover:text-danger"
                        >
                          <ShieldOffIcon className="size-3.5" aria-hidden />
                          {t("revoke")}
                        </Button>
                      ) : null}
                      {key.state === "revoked" || key.state === "expired" ? (
                        <span className="text-sm text-ink-500">
                          {t("notRevocable")}
                        </span>
                      ) : null}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </section>
      </div>

      <ConfirmDialog
        open={rotateOpen}
        onOpenChange={setRotateOpen}
        icon={<RotateCwIcon />}
        title={t("rotateDialog.title")}
        description={t("rotateDialog.body")}
        onConfirm={rotate}
        confirmLabel={t("rotateDialog.confirm")}
        confirmingLabel={t("rotateDialog.confirming")}
        cancelLabel={t("cancel")}
        confirming={rotateMutation.isPending}
        destructive
        contentClassName="sm:max-w-dialog"
      />

      <ConfirmDialog
        open={revokeKey !== null}
        onOpenChange={(open) => {
          if (!open) setRevokeKey(null);
        }}
        icon={<ShieldOffIcon />}
        title={t("revokeDialog.title")}
        description={t("revokeDialog.body", {
          prefix: revokeKey ? shortResourceId(revokeKey.id) : "",
        })}
        onConfirm={revoke}
        confirmLabel={t("revokeDialog.confirm")}
        confirmingLabel={t("revokeDialog.confirming")}
        cancelLabel={t("cancel")}
        confirming={revokeMutation.isPending}
        contentClassName="sm:max-w-dialog"
      />
    </>
  );
}
