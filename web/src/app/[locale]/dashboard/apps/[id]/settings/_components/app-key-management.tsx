"use client";

import { CopyIcon, RotateCwIcon, ShieldOffIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import type { RpcAppKey, RpcAppKeyState } from "@/api/apps/client";
import { isApiError } from "@/api/client";
import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
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
  return (
    <div className="flex flex-col divide-y divide-ink-wash" aria-busy="true">
      {["first", "second"].map((key) => (
        <div key={key} className="p-4">
          <Skeleton className="h-28 w-full rounded-xl" />
        </div>
      ))}
    </div>
  );
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
      <section
        data-slot="app-key-management"
        aria-labelledby="app-access-keys-title"
        className="overflow-hidden rounded-3xl bg-table-frame"
      >
        <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
          <div className="min-w-0 flex-1 basis-52">
            <h2
              id="app-access-keys-title"
              className="text-sm font-semibold text-ink-900"
            >
              {t("title")}
            </h2>
            <p className="mt-0.5 text-2xs leading-snug text-ink-500">
              {t("subtitle")}
            </p>
          </div>
          <div className="shrink-0">
            <Button
              type="button"
              variant="soft"
              size="sm"
              onClick={() => setRotateOpen(true)}
              disabled={rotateMutation.isPending}
              className="rounded-xl"
            >
              <RotateCwIcon className="size-4" aria-hidden />
              {t("rotate")}
            </Button>
          </div>
        </header>

        <div className="mx-1 mb-1 overflow-hidden rounded-table-pill bg-surface">
          {query.isPending ? <KeyListSkeleton /> : null}

          {query.isError ? (
            <div role="alert" className="m-4 rounded-lg bg-danger-soft p-4">
              <p className="font-medium text-danger">{t("error.title")}</p>
              <p className="mt-1 text-sm text-danger">{t("error.body")}</p>
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
          ) : null}

          {query.data && query.data.items.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-ink-500">
              {t("empty")}
            </p>
          ) : null}

          {query.data && query.data.items.length > 0 ? (
            <div className="overflow-x-auto">
              <table
                aria-label={t("title")}
                className="w-full min-w-240 table-fixed border-collapse"
              >
                <colgroup>
                  <col />
                  <col className="w-32" />
                  <col className="w-36" />
                  <col className="w-36" />
                  <col className="w-36" />
                  <col className="w-28" />
                </colgroup>
                <thead className="border-b border-ink-wash">
                  <tr>
                    <th className="px-4 py-4 text-left text-sm font-semibold text-ink-900">
                      {t("columns.apiKey")}
                    </th>
                    <th className="px-4 py-4 text-left text-sm font-semibold text-ink-900">
                      {t("columns.state")}
                    </th>
                    <th className="px-4 py-4 text-left text-sm font-semibold text-ink-900">
                      {t("columns.expiresAt")}
                    </th>
                    <th className="px-4 py-4 text-left text-sm font-semibold text-ink-900">
                      {t("columns.revokedAt")}
                    </th>
                    <th className="px-4 py-4 text-left text-sm font-semibold text-ink-900">
                      {t("columns.createdAt")}
                    </th>
                    <th className="px-4 py-4 text-right text-sm font-semibold text-ink-900">
                      {t("columns.actions")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-wash">
                  {query.data.items.map((key) => {
                    const revocable =
                      key.state === "active" || key.state === "grace";

                    return (
                      <tr key={key.id}>
                        <td className="min-w-0 px-4 py-4 align-top">
                          <div className="flex min-w-0 items-start gap-2">
                            <code className="min-w-0 flex-1 break-all font-mono text-sm text-ink-700">
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
                        </td>
                        <td className="px-4 py-4 align-top">
                          <Badge variant={STATE_VARIANT[key.state]} dot>
                            {t(`states.${key.state}`)}
                          </Badge>
                        </td>
                        <td className="px-4 py-4 align-top text-sm text-ink-600">
                          {key.expires_at ? (
                            <Time value={key.expires_at} />
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="px-4 py-4 align-top text-sm text-ink-600">
                          {key.revoked_at ? (
                            <Time value={key.revoked_at} />
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="px-4 py-4 align-top text-sm text-ink-600">
                          <Time value={key.created_at} />
                        </td>
                        <td className="px-4 py-4 text-right align-top">
                          {revocable ? (
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
                          ) : (
                            <span className="text-sm text-ink-400">
                              {t("notRevocable")}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      </section>

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
        destructive={false}
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
