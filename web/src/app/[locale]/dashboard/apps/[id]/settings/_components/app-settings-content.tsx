"use client";

import { CopyIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { type FormEvent, useEffect, useState } from "react";
import { toast } from "sonner";
import type { UpdateRpcAppParams } from "@/api/apps/client";
import { isApiError } from "@/api/client";
import { Field } from "@/components/patterns/form-field";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useAppQuery, useUpdateAppMutation } from "@/hooks/use-apps";
import { copyToClipboard } from "@/lib/clipboard";
import { DeleteAppDialog } from "./delete-app-dialog";

const APP_DETAILS_FORM_ID = "app-settings-details-form";

function apiErrorMessage(error: unknown, fallback: string): string {
  return isApiError(error) && error.message ? error.message : fallback;
}

/**
 * Per-app general settings page: editable app details and an isolated
 * destructive delete action. Access-key lifecycle has its own settings route.
 */
export function AppSettingsContent({ appId }: { appId: string }) {
  const t = useTranslations("dashboard.apps");
  const { data: app, isLoading, isError, refetch } = useAppQuery(appId);
  const mutation = useUpdateAppMutation();

  const [name, setName] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [deleteOpen, setDeleteOpen] = useState(false);

  // Mirror the server values whenever they change (initial load, or after a
  // successful save refreshes the detail).
  useEffect(() => {
    if (app) {
      setName(app.name);
      setEnabled(app.enabled);
    }
  }, [app]);

  const handleCopy = async (text: string) => {
    const ok = await copyToClipboard(text);
    if (ok) toast.success(t("toast.copyOk"));
    else toast.error(t("toast.copyError"));
  };

  if (isLoading) {
    return (
      <div className="flex w-full flex-col gap-6">
        <div className="flex flex-col gap-3">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-4 w-80" />
        </div>
        <Skeleton className="h-96 w-full rounded-2xl" />
        <Skeleton className="h-32 w-full rounded-2xl" />
      </div>
    );
  }

  if (isError || !app) {
    return (
      <div
        role="alert"
        className="mx-auto flex max-w-prose-narrow flex-col items-center gap-2 py-14 text-center"
      >
        <p className="text-lg font-semibold text-ink-900">
          {t("detail.notFound.title")}
        </p>
        <p className="text-md text-ink-500">{t("detail.notFound.body")}</p>
        <button
          type="button"
          onClick={() => refetch()}
          className="mt-2 inline-flex h-9 items-center rounded-md bg-brand-soft px-4 text-sm font-semibold text-brand transition-colors hover:bg-brand hover:text-white"
        >
          {t("error.retry")}
        </button>
      </div>
    );
  }

  const trimmedName = name.trim();
  const changed = trimmedName !== app.name || enabled !== app.enabled;
  const dirty = trimmedName.length > 0 && changed;

  const save = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!dirty || mutation.isPending) return;
    const input: UpdateRpcAppParams = { expected_version: app.version };
    if (trimmedName !== app.name) input.name = trimmedName;
    if (enabled !== app.enabled) input.enabled = enabled;
    mutation.mutate(
      { id: app.id, input },
      {
        onSuccess: () => toast.success(t("toast.updated")),
        onError: (error) =>
          toast.error(apiErrorMessage(error, t("toast.updateError"))),
      },
    );
  };

  return (
    <div className="flex w-full flex-col gap-7">
      <header className="flex flex-col gap-1.5">
        <h1 className="text-3xl font-bold tracking-tight text-ink-900">
          {t("settings.title")}
        </h1>
        <p className="max-w-prose-narrow text-md text-ink-500">
          {t("settings.subtitle")}
        </p>
      </header>

      <div
        data-slot="app-settings-content-area"
        className="flex flex-col gap-7"
      >
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">
              {t("settings.details.title")}
            </CardTitle>
            <CardDescription>
              {t("settings.details.description")}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form
              id={APP_DETAILS_FORM_ID}
              className="flex flex-col gap-6"
              onSubmit={save}
            >
              <div className="grid gap-6 md:grid-cols-2">
                <Field
                  label={t("form.name")}
                  htmlFor="app-name"
                  hint={t("settings.details.nameHint")}
                  labelClassName="text-sm font-medium"
                >
                  <Input
                    id="app-name"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder={t("form.namePlaceholder")}
                    maxLength={128}
                    disabled={mutation.isPending}
                    className="rounded-xl"
                  />
                </Field>

                <Field
                  label={t("settings.details.appId")}
                  hint={t("settings.details.appIdHint")}
                  labelClassName="text-sm font-medium"
                >
                  <div className="flex h-12 items-center gap-2 rounded-xl bg-ink-wash pr-1 pl-3">
                    <code className="min-w-0 flex-1 truncate font-mono text-md tabular-nums text-ink-700">
                      {app.id}
                    </code>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => handleCopy(app.id)}
                    >
                      <CopyIcon className="size-3.5" aria-hidden />
                      {t("settings.details.copy")}
                    </Button>
                  </div>
                </Field>
              </div>

              <div
                data-slot="app-state-actions"
                className="flex items-center gap-3 rounded-xl bg-ink-wash px-4 py-3"
              >
                <div className="min-w-0">
                  <p
                    id="app-enabled-label"
                    className="text-sm font-semibold text-ink-900"
                  >
                    {t("form.enabled")}
                  </p>
                  <p className="mt-0.5 text-xs text-ink-500">
                    {t("form.enabledHint")}
                  </p>
                </div>
                <Switch
                  id="app-enabled"
                  checked={enabled}
                  onCheckedChange={setEnabled}
                  disabled={mutation.isPending}
                  aria-labelledby="app-enabled-label"
                />
              </div>

              {changed ? (
                <div className="flex justify-end">
                  <Button type="submit" disabled={!dirty || mutation.isPending}>
                    {mutation.isPending
                      ? t("dialog.saving")
                      : t("settings.details.save")}
                  </Button>
                </div>
              ) : null}
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">
              {t("settings.danger.title")}
            </CardTitle>
            <CardDescription>
              {t("settings.danger.description")}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              type="button"
              variant="destructive"
              onClick={() => setDeleteOpen(true)}
            >
              {t("settings.danger.delete")}
            </Button>
          </CardContent>
        </Card>
      </div>

      <DeleteAppDialog
        app={app}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
      />
    </div>
  );
}
