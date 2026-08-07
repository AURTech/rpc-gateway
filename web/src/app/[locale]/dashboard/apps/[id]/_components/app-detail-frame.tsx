"use client";

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import type { RpcAppDetail } from "@/api/apps/client";
import { Skeleton } from "@/components/ui/skeleton";
import { useAppQuery } from "@/hooks/use-apps";

/**
 * Shared chrome for the app's sub-pages (Overview, Gateways, Usage): loads the app,
 * renders the loading/not-found states and the title header, then hands the
 * non-secret app detail to `children`.
 * Desktop keeps the bounded-viewport layout so headers stay put and only the
 * page body scrolls; mobile flows with the page.
 */
export function AppDetailFrame({
  appId,
  children,
  headerAction,
}: {
  appId: string;
  children: (app: RpcAppDetail) => ReactNode;
  headerAction?: ReactNode;
}) {
  const t = useTranslations("dashboard.apps");
  const { data: app, isLoading, isError, refetch } = useAppQuery(appId);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-3">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-4 w-80" />
        </div>
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  if (isError || !app) {
    return (
      <div className="flex flex-col gap-6">
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
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 md:h-app-detail md:min-h-0">
      <header className="grid shrink-0 grid-cols-1 items-start gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,auto)] lg:gap-x-6">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="truncate text-3xl font-bold tracking-tight text-ink-900">
            {app.name}
          </h1>
          <code className="font-mono text-xs text-ink-400">{app.id}</code>
        </div>
        {headerAction ? (
          <div className="min-w-0 lg:justify-self-end">{headerAction}</div>
        ) : null}
      </header>
      {children(app)}
    </div>
  );
}
