"use client";

import { ArrowRight, ChevronRight, Plus } from "lucide-react";
import { useTranslations } from "next-intl";

import type { RpcAppListItem } from "@/api/apps/client";
import { MotionList, MotionListItem } from "@/components/patterns/motion-list";
import { Button } from "@/components/ui/button";
import { ChainGroup } from "@/components/ui/chain-group";
import { Skeleton } from "@/components/ui/skeleton";
import { useAppsQuery } from "@/hooks/use-apps";
import { Link } from "@/i18n/navigation";
import { isRpcChain } from "@/lib/rpc-chain";
import { cn } from "@/lib/utils";

// Overview shows just a glance of the most recent apps; the full list (search,
// pagination) lives on /dashboard/apps.
const PREVIEW_SIZE = 3;

export function OverviewAppsPanel({ className }: { className?: string }) {
  const t = useTranslations("dashboard.overview.apps");
  const query = useAppsQuery({ size: PREVIEW_SIZE, sort: "DESC" });
  const items = query.data?.items ?? [];

  return (
    <section
      aria-label={t("title")}
      className={cn(
        "flex flex-col rounded-xl bg-surface p-5 shadow-section",
        className,
      )}
    >
      <header className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-ink-900">{t("title")}</h2>
        <Button asChild size="sm" className="shrink-0">
          <Link href="/dashboard/apps/new">
            <Plus className="size-4" />
            {t("newApp")}
          </Link>
        </Button>
      </header>

      <div className="mt-4 flex flex-1 flex-col">
        {query.isPending ? (
          <ul className="flex flex-col gap-1">
            {Array.from({ length: 3 }, (_, i) => i).map((i) => (
              <li
                key={i}
                aria-busy="true"
                className="flex items-center gap-3 px-3 py-3"
              >
                <Skeleton className="h-4 w-40" />
                <Skeleton className="ml-auto h-5 w-20 rounded-full" />
              </li>
            ))}
          </ul>
        ) : query.isError ? (
          <ErrorState
            title={t("error.title")}
            retryLabel={t("error.retry")}
            onRetry={() => query.refetch()}
          />
        ) : items.length === 0 ? (
          <EmptyState
            title={t("empty.title")}
            body={t("empty.body")}
            cta={t("empty.cta")}
          />
        ) : (
          <>
            {/* `mb-4`, not just the button's `mt-auto`: the panel is stretched
                to the Resources card's height, so when the rows fill it the
                auto margin collapses to 0 and the last row's hover fill — which
                covers its whole padded box — runs straight into the button. */}
            <MotionList as="ul" className="mb-4 flex flex-col gap-1">
              {items.map((app) => (
                <AppRow key={app.id} app={app} />
              ))}
            </MotionList>
            <Button asChild size="sm" className="mt-auto self-start">
              <Link href="/dashboard/apps">
                {t("manageAll")}
                <ArrowRight className="size-4" aria-hidden />
              </Link>
            </Button>
          </>
        )}
      </div>
    </section>
  );
}

function AppRow({ app }: { app: RpcAppListItem }) {
  // Server may send chain slugs the frontend doesn't know yet; drop those.
  const chains = app.chains.filter(isRpcChain);
  return (
    <MotionListItem as="li">
      <Link
        href={`/dashboard/apps/${app.id}`}
        className="group flex items-center gap-3 rounded-lg px-3 py-3 transition-colors hover:bg-row-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand/40"
      >
        <span className="min-w-0 flex-1 truncate text-md font-semibold text-ink-900">
          {app.name}
        </span>
        <ChainGroup chains={chains} />
        <ChevronRight
          className="size-4 shrink-0 text-ink-400 transition group-hover:translate-x-0.5 group-hover:text-ink-700"
          aria-hidden
        />
      </Link>
    </MotionListItem>
  );
}

function EmptyState({
  title,
  body,
  cta,
}: {
  title: string;
  body: string;
  cta: string;
}) {
  return (
    <div className="m-auto flex max-w-prose-narrow flex-col items-center gap-2 px-4 py-10 text-center">
      <p className="text-lg font-semibold text-ink-900">{title}</p>
      <p className="text-md text-ink-500">{body}</p>
      <Button asChild size="sm" className="mt-2">
        <Link href="/dashboard/apps/new">
          <Plus className="size-4" />
          {cta}
        </Link>
      </Button>
    </div>
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
      <Button type="button" size="sm" onClick={onRetry} className="mt-1">
        {retryLabel}
      </Button>
    </div>
  );
}
