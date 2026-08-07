"use client";

import { ChevronRight } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { useOverviewQuery } from "@/hooks/use-overview";
import { Link } from "@/i18n/navigation";
import { cn } from "@/lib/utils";

/**
 * Resource stat card beside Overview's apps panel: plain label + value
 * rows without charts for endpoint/app counts off
 * `/v2/overview`. Each row links to its management page. The counts are
 * point-in-time entity totals, so the card takes no range selector.
 */
export function OverviewResourcesCard({ className }: { className?: string }) {
  const t = useTranslations("dashboard.overview.resources");
  const locale = useLocale();
  const query = useOverviewQuery();

  const integer = useMemo(() => new Intl.NumberFormat(locale), [locale]);

  return (
    <section
      aria-label={t("ariaLabel")}
      className={cn(
        "flex flex-col rounded-xl bg-surface p-5 shadow-section",
        className,
      )}
    >
      <header className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-ink-900">{t("title")}</h2>
      </header>

      <div className="mt-4 flex flex-1 flex-col">
        {query.isPending ? (
          <ResourceRowsSkeleton />
        ) : query.isError || !query.data ? (
          <ErrorState
            title={t("error.title")}
            retryLabel={t("error.retry")}
            onRetry={() => query.refetch()}
          />
        ) : (
          <ul className="flex flex-col gap-1">
            <ResourceRow
              href="/dashboard/endpoints"
              label={t("endpoints")}
              value={integer.format(query.data.active_endpoint_total)}
              total={integer.format(query.data.endpoint_total)}
            />
            <ResourceRow
              href="/dashboard/providers"
              label={t("providers")}
              value={integer.format(query.data.provider_total)}
            />
            <ResourceRow
              href="/dashboard/apps"
              label={t("apps")}
              value={integer.format(query.data.app_total)}
            />
          </ul>
        )}
      </div>
    </section>
  );
}

function ResourceRow({
  href,
  label,
  value,
  total,
}: {
  href: string;
  label: string;
  value: string;
  // When present, renders as "value / total".
  total?: string;
}) {
  return (
    <li>
      <Link
        href={href}
        className="group flex items-center gap-3 rounded-lg px-3 py-3 transition-colors hover:bg-row-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand/40"
      >
        <span className="min-w-0 flex-1 truncate text-md text-ink-700">
          {label}
        </span>
        <span className="shrink-0 text-md font-semibold tabular-nums text-ink-900">
          {value}
          {total !== undefined ? (
            <span className="font-normal text-ink-400"> / {total}</span>
          ) : null}
        </span>
        <ChevronRight
          className="size-4 shrink-0 text-ink-400 transition group-hover:translate-x-0.5 group-hover:text-ink-700"
          aria-hidden
        />
      </Link>
    </li>
  );
}

function ResourceRowsSkeleton() {
  return (
    <ul aria-busy="true" className="flex flex-col gap-1">
      {[0, 1, 2].map((i) => (
        <li key={i} className="flex items-center gap-3 px-3 py-3">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="ml-auto h-4 w-12" />
        </li>
      ))}
    </ul>
  );
}

function ErrorState({
  title,
  retryLabel,
  onRetry,
}: {
  title: string;
  retryLabel: string;
  onRetry: () => void;
}) {
  return (
    <div
      role="alert"
      className="m-auto flex max-w-prose-narrow flex-col items-center gap-2 px-4 py-10 text-center"
    >
      <p className="text-md font-medium text-ink-900">{title}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-1 inline-flex h-9 items-center rounded-md bg-ink-wash px-4 text-sm font-semibold text-ink-700 transition-colors hover:text-ink-900"
      >
        {retryLabel}
      </button>
    </div>
  );
}
