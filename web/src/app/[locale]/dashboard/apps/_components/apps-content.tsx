"use client";

import { ChevronRight, Plus, Search } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import type { RpcAppListItem } from "@/api/apps/client";
import { MotionList, MotionListItem } from "@/components/patterns/motion-list";
import { Button } from "@/components/ui/button";
import { ChainGroup } from "@/components/ui/chain-group";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Time } from "@/components/ui/time";
import { useInfiniteAppsQuery } from "@/hooks/use-apps";
import { useInfiniteScroll } from "@/hooks/use-infinite-scroll";
import { Link } from "@/i18n/navigation";
import { isRpcChain } from "@/lib/rpc-chain";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 10;

// Hairline under the column header only — rows themselves are separated by
// whitespace + hover wash, not dividers.
const HEADER_DIVIDER = "shadow-[inset_0_-1px_0_rgb(15_23_42_/_0.04)]";

// Shared column widths so the header row and every data row line up. Chains and
// Created collapse on narrow screens, leaving Name + the drill-in chevron.
const COL = {
  name: "min-w-0 flex-1",
  chains: "hidden w-40 shrink-0 md:block",
  created: "hidden w-40 shrink-0 md:block",
  chevron: "flex w-8 shrink-0 justify-end",
};

function ListHeader() {
  const t = useTranslations("dashboard.apps");
  return (
    <div
      className={cn(
        "flex items-center gap-4 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-ink-500",
        HEADER_DIVIDER,
      )}
    >
      <div className={COL.name}>{t("table.name")}</div>
      <div className={COL.chains}>{t("table.chains")}</div>
      <div className={COL.created}>{t("table.created")}</div>
      <div className={COL.chevron} aria-hidden />
    </div>
  );
}

function SkeletonRow() {
  return (
    <div aria-busy="true" className="flex items-center gap-4 px-4 py-3.5">
      <div className={COL.name}>
        <Skeleton className="h-4 w-40" />
      </div>
      <div className={COL.chains}>
        <Skeleton className="h-5 w-24 rounded-full" />
      </div>
      <div className={COL.created}>
        <Skeleton className="h-4 w-28" />
      </div>
      <div className={COL.chevron} aria-hidden />
    </div>
  );
}

function AppListRow({ app }: { app: RpcAppListItem }) {
  // Server may send chain slugs the frontend doesn't know yet; drop those.
  const chains = app.chains.filter(isRpcChain);

  // The whole row is the affordance — a real link, so keyboard, middle-click,
  // and "open in new tab" all work for free. The trailing chevron is the quiet
  // drill-in cue (no redundant button repeating the row's own click target).
  return (
    <Link
      href={`/dashboard/apps/${app.id}`}
      className="group flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-row-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand/40"
    >
      <div className={COL.name}>
        <span className="block truncate text-md font-semibold text-ink-900">
          {app.name}
        </span>
      </div>
      <div className={COL.chains}>
        <ChainGroup chains={chains} />
      </div>
      <div className={cn(COL.created, "text-sm tabular-nums text-ink-500")}>
        <Time value={app.created_at} />
      </div>
      <div className={COL.chevron}>
        <ChevronRight
          className="size-4 text-ink-400 transition group-hover:translate-x-0.5 group-hover:text-ink-700"
          aria-hidden
        />
      </div>
    </Link>
  );
}

export function AppsContent() {
  const t = useTranslations("dashboard.apps");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");

  // Debounce the search box so we don't refetch on every keystroke.
  useEffect(() => {
    const id = setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => clearTimeout(id);
  }, [searchInput]);

  const query = useInfiniteAppsQuery({
    size: PAGE_SIZE,
    sort: "DESC",
    search: search || undefined,
  });
  const items = query.data?.pages.flatMap((p) => p.items) ?? [];
  const hasFilter = search.length > 0;

  const sentinelRef = useInfiniteScroll({
    hasMore: query.hasNextPage,
    isFetchingMore: query.isFetchingNextPage,
    onLoadMore: () => query.fetchNextPage(),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="relative w-full max-w-sm">
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          {/* Borderless soft-fill search field via the shared `Input` (no
           * border, brand/30 focus ring, no box-shadow transition → no fading
           * focus edge). Plain text input (no `type=search`) to avoid any
           * browser-native search-field chrome. */}
          <Input
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder={t("search.placeholder")}
            aria-label={t("search.aria")}
            className="rounded-2xl pl-9"
          />
        </div>
        <Button asChild size="xl">
          <Link href="/dashboard/apps/new">
            <Plus className="size-4" />
            {t("cta.newApp")}
          </Link>
        </Button>
      </div>

      <div className="overflow-hidden rounded-2xl bg-surface shadow-elevated">
        <ListHeader />

        {query.isLoading
          ? Array.from({ length: PAGE_SIZE }, (_, i) => i).map((i) => (
              <SkeletonRow key={i} />
            ))
          : null}

        {!query.isLoading && query.isError ? (
          <div
            role="alert"
            className="mx-auto flex max-w-prose-narrow flex-col items-center gap-2 px-4 py-14 text-center"
          >
            <p className="text-lg font-semibold text-ink-900">
              {t("error.title")}
            </p>
            <p className="text-md text-ink-500">{t("error.body")}</p>
            <button
              type="button"
              onClick={() => query.refetch()}
              className="mt-2 inline-flex h-9 items-center rounded-md bg-brand-soft px-4 text-sm font-semibold text-brand transition-colors hover:bg-brand hover:text-white"
            >
              {t("error.retry")}
            </button>
          </div>
        ) : null}

        {!query.isLoading && !query.isError && items.length === 0 ? (
          <div className="mx-auto flex max-w-prose-narrow flex-col items-center gap-2 px-4 py-14 text-center">
            <p className="text-lg font-semibold text-ink-900">
              {hasFilter ? t("filteredEmpty.title") : t("empty.title")}
            </p>
            <p className="text-md text-ink-500">
              {hasFilter ? t("filteredEmpty.body") : t("empty.body")}
            </p>
            {hasFilter ? (
              <button
                type="button"
                onClick={() => setSearchInput("")}
                className="mt-2 inline-flex h-9 items-center rounded-md bg-brand-soft px-4 text-sm font-semibold text-brand transition-colors hover:bg-brand hover:text-white"
              >
                {t("filteredEmpty.cta")}
              </button>
            ) : (
              <Link
                href="/dashboard/apps/new"
                className="mt-2 inline-flex h-9 items-center rounded-md bg-brand-soft px-4 text-sm font-semibold text-brand transition-colors hover:bg-brand hover:text-white"
              >
                {t("empty.cta")}
              </Link>
            )}
          </div>
        ) : null}

        {!query.isLoading && !query.isError ? (
          <MotionList>
            {items.map((app) => (
              <MotionListItem key={app.id}>
                <AppListRow app={app} />
              </MotionListItem>
            ))}
          </MotionList>
        ) : null}

        {/* Scroll-loading: a skeleton while the next page is in flight, plus a
         * sentinel the observer watches once the first page is on screen. */}
        {!query.isLoading && !query.isError && items.length > 0 ? (
          <>
            {query.isFetchingNextPage ? <SkeletonRow /> : null}
            {query.hasNextPage ? (
              <div ref={sentinelRef} aria-hidden className="h-px" />
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  );
}
