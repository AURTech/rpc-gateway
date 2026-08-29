"use client";

import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  EyeIcon,
  EyeOffIcon,
  LoaderCircleIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import {
  getProviderCredential,
  type ProviderEndpoint,
} from "@/api/providers/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChainIcon } from "@/components/ui/chain-icon";
import { CompactTablePager } from "@/components/ui/compact-table-pager";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { Time } from "@/components/ui/time";
import { Link } from "@/i18n/navigation";
import { CHAIN_CATALOG } from "@/lib/blockchain";
import { cn } from "@/lib/utils";

import {
  endpointDiscovery,
  endpointRegistry,
  type ProviderRecord,
} from "./provider-model";
import { ProviderNetworkChips } from "./provider-network-visuals";
import { useProviderEndpoints, useProviderRuns } from "./use-providers";

type ExpansionTab = "provider" | "endpoints" | "activity";
const EXPANSION_PAGE_SIZE = 5;

interface ProviderRowExpansionProps {
  provider: ProviderRecord;
}

function ProviderRowExpansion({ provider }: ProviderRowExpansionProps) {
  const t = useTranslations("dashboard.endpointProviders");
  const [tab, setTab] = useState<ExpansionTab>("provider");
  const [visitedTabs, setVisitedTabs] = useState<Set<ExpansionTab>>(
    () => new Set(["provider"]),
  );
  const endpointTotal =
    provider.endpoint_counts.present + provider.endpoint_counts.missing;

  function changeTab(next: ExpansionTab) {
    setVisitedTabs((current) => {
      if (current.has(next)) return current;
      const visited = new Set(current);
      visited.add(next);
      return visited;
    });
    setTab(next);
  }

  return (
    <div className="flex min-w-0 flex-col">
      <Tabs
        mode="tab"
        value={tab}
        onChange={changeTab}
        options={[
          { value: "provider", label: t("rowExpansion.tabs.provider") },
          {
            value: "endpoints",
            label: t("rowExpansion.tabs.endpointsCount", {
              count: endpointTotal,
            }),
          },
          { value: "activity", label: t("rowExpansion.tabs.activity") },
        ]}
        ariaLabel={t("rowExpansion.tabs.label")}
        idBase={`provider-${provider.id}-expansion-tab`}
        panelIdForValue={(value) =>
          `provider-${provider.id}-expansion-panel-${value}`
        }
        variant="underline"
      />

      <div className="grid min-w-0">
        {(["provider", "endpoints", "activity"] as const).map((panel) => (
          <div
            key={panel}
            id={`provider-${provider.id}-expansion-panel-${panel}`}
            role="tabpanel"
            aria-labelledby={`provider-${provider.id}-expansion-tab-${panel}`}
            aria-hidden={tab !== panel}
            inert={tab !== panel ? true : undefined}
            className={cn("min-w-0", tab !== panel && "hidden")}
          >
            {visitedTabs.has(panel) ? (
              panel === "provider" ? (
                <ProviderFacts provider={provider} active={tab === panel} />
              ) : panel === "endpoints" ? (
                <ProviderEndpoints provider={provider} />
              ) : (
                <ProviderActivity provider={provider} />
              )
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function ProviderFacts({
  provider,
  active,
}: {
  provider: ProviderRecord;
  active: boolean;
}) {
  const t = useTranslations("dashboard.endpointProviders");
  const [secret, setSecret] = useState<string | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const activeRef = useRef(active);
  const credentialRequest = useRef(0);

  useEffect(() => {
    activeRef.current = active;
    if (active) return;
    credentialRequest.current += 1;
    setSecret(null);
    setRevealed(false);
    setLoading(false);
    setError(false);
  }, [active]);

  useEffect(
    () => () => {
      activeRef.current = false;
      credentialRequest.current += 1;
    },
    [],
  );

  async function toggleCredential() {
    if (revealed) {
      setRevealed(false);
      return;
    }
    if (secret) {
      setRevealed(true);
      return;
    }
    setLoading(true);
    setError(false);
    const request = ++credentialRequest.current;
    try {
      const credential = await getProviderCredential(provider.id);
      if (!activeRef.current || credentialRequest.current !== request) return;
      setSecret(credential.secret);
      setRevealed(true);
    } catch {
      if (!activeRef.current || credentialRequest.current !== request) return;
      setError(true);
    } finally {
      if (activeRef.current && credentialRequest.current === request) {
        setLoading(false);
      }
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <dl className="grid grid-cols-12 gap-x-8 gap-y-5">
        <Fact
          className="col-span-12 sm:col-span-6"
          label={t("rowExpansion.provider.networks")}
        >
          <ProviderNetworkChips
            networks={provider.networks}
            vendor={provider.vendor}
          />
        </Fact>
        <Fact
          className="col-span-6 sm:col-span-3"
          label={t("rowExpansion.provider.autoSync")}
        >
          {t(
            provider.sync_enabled
              ? "rowExpansion.provider.on"
              : "rowExpansion.provider.off",
          )}
        </Fact>
        <Fact
          className="col-span-6 sm:col-span-3"
          label={t("rowExpansion.provider.apps")}
        >
          <span className="tabular-nums">{provider.connected_app_count}</span>
        </Fact>
      </dl>

      <dl className="grid grid-cols-12 gap-x-8 gap-y-5 border-t border-table-frame pt-5">
        <div className="col-span-12 min-w-0 md:col-span-6">
          <dt className="text-xs font-medium text-ink-500">
            {t("rowExpansion.provider.providerCredential")}
          </dt>
          <dd className="mt-1 min-w-0">
            <p className="text-xs text-ink-500">
              {t("rowExpansion.provider.providerCredentialPurpose")}
            </p>
            <span className="mt-2 flex min-w-0 items-center gap-1.5 font-mono text-xs text-ink-700">
              <span className="min-w-0 break-all">
                {provider.credential.has_secret
                  ? revealed && secret
                    ? secret
                    : "••••••••••••"
                  : t("rowExpansion.provider.missing")}
              </span>
              {provider.credential.has_secret ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  className="shrink-0 text-ink-500"
                  disabled={loading}
                  aria-label={
                    revealed
                      ? t("rowExpansion.provider.hideCredential")
                      : t("rowExpansion.provider.showCredential")
                  }
                  aria-pressed={revealed}
                  onClick={toggleCredential}
                >
                  {loading ? (
                    <LoaderCircleIcon className="animate-spin" aria-hidden />
                  ) : revealed ? (
                    <EyeOffIcon aria-hidden />
                  ) : (
                    <EyeIcon aria-hidden />
                  )}
                </Button>
              ) : null}
            </span>
            {error ? (
              <p className="mt-1 text-xs text-danger" aria-live="polite">
                {t("rowExpansion.provider.credentialError")}
              </p>
            ) : null}
          </dd>
        </div>

        <div className="col-span-12 min-w-0 md:col-span-6">
          <dt className="text-xs font-medium text-ink-500">
            {t("rowExpansion.provider.endpointAuthentication")}
          </dt>
          <dd className="mt-1 text-xs text-ink-500">
            <p>{t("rowExpansion.provider.endpointAuthenticationPurpose")}</p>
            <p className="mt-1">
              {t(`rowExpansion.provider.endpointAuth.${provider.vendor}`)}
            </p>
          </dd>
        </div>
      </dl>
    </div>
  );
}

function ProviderEndpoints({ provider }: { provider: ProviderRecord }) {
  const t = useTranslations("dashboard.endpointProviders.rowExpansion");
  const [page, setPage] = useState(1);
  const query = useProviderEndpoints(provider.id, page, EXPANSION_PAGE_SIZE);
  const items = (query.data?.items ?? []) as ProviderEndpoint[];

  useEffect(() => {
    if (query.data && page > query.data.max_page) {
      setPage(Math.max(1, query.data.max_page));
    }
  }, [page, query.data]);

  if (query.isLoading) return <ListSkeleton />;
  if (query.isError) {
    return (
      <InlineError
        title={t("endpoints.errorTitle")}
        body={t("endpoints.errorBody")}
        retry={t("retry")}
        onRetry={() => query.refetch()}
      />
    );
  }
  if (!items.length) {
    return (
      <EmptyState
        title={t("endpoints.emptyTitle")}
        body={t("endpoints.emptyBody")}
      />
    );
  }

  return (
    <section
      aria-label={t("endpoints.listLabel")}
      className="flex min-w-0 flex-col gap-2"
    >
      {query.data && query.data.total > EXPANSION_PAGE_SIZE ? (
        <CompactTablePager
          page={query.data.page}
          maxPage={query.data.max_page}
          pageSize={query.data.size}
          pageItemCount={query.data.items.length}
          total={query.data.total}
          onPageChange={setPage}
          rangeLabel={({ from, to, total }) => t("range", { from, to, total })}
          prevLabel={t("previous")}
          nextLabel={t("next")}
          loading={query.isPlaceholderData}
        />
      ) : null}

      <div
        className="hidden grid-cols-12 gap-x-6 border-b border-table-frame pb-2 text-xs font-medium text-ink-500 md:grid"
        aria-hidden
      >
        <span className="col-span-4">{t("endpoints.columns.endpoint")}</span>
        <span className="col-span-2">{t("endpoints.columns.network")}</span>
        <span className="col-span-2">{t("endpoints.columns.protocol")}</span>
        <span className="col-span-2">{t("endpoints.columns.discovery")}</span>
        <span className="col-span-2 text-right">
          {t("endpoints.columns.lastSeen")}
        </span>
      </div>

      <ul
        aria-busy={query.isPlaceholderData}
        inert={query.isPlaceholderData ? true : undefined}
        className={cn(
          "divide-y divide-table-frame transition-opacity",
          query.isPlaceholderData && "pointer-events-none opacity-60",
        )}
      >
        {items.map((item) => (
          <ProviderEndpointItem key={item.external_id} item={item} />
        ))}
      </ul>
    </section>
  );
}

function ProviderEndpointItem({ item }: { item: ProviderEndpoint }) {
  const t = useTranslations("dashboard.endpointProviders.rowExpansion");
  const endpoint = item.endpoint;
  const discovery = endpointDiscovery(item);
  const registry = endpointRegistry(item);

  return (
    <li className="grid grid-cols-12 items-center gap-x-6 gap-y-3 py-3.5 first:pt-1 last:pb-1">
      <div className="col-span-12 flex min-w-0 items-center gap-3 md:col-span-4">
        <ChainIcon
          chain={endpoint.chain}
          network={endpoint.network}
          className="size-5 shrink-0"
        />
        <span className="min-w-0 flex-1">
          {registry === "active" ? (
            <Link
              href={`/dashboard/endpoints?q=${encodeURIComponent(endpoint.id)}&expanded=${encodeURIComponent(endpoint.id)}`}
              className="block truncate rounded-sm font-semibold text-ink-900 hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
            >
              {endpoint.name}
            </Link>
          ) : (
            <span className="block truncate font-semibold text-ink-900">
              {endpoint.name}
            </span>
          )}
          <span
            className="block truncate font-mono text-xs leading-5 text-ink-500"
            title={endpoint.effective_url ?? endpoint.url}
          >
            {endpoint.effective_url ?? endpoint.url}
          </span>
        </span>
      </div>
      <span className="col-span-6 text-sm text-ink-700 md:col-span-2">
        <span className="mr-1 text-xs text-ink-400 md:hidden">
          {t("endpoints.columns.network")}
        </span>
        {CHAIN_CATALOG[endpoint.chain].label} · {endpoint.network}
      </span>
      <span className="col-span-6 text-right font-mono text-xs text-ink-700 md:col-span-2 md:text-left">
        <span className="mr-1 font-sans text-xs text-ink-400 md:hidden">
          {t("endpoints.columns.protocol")}
        </span>
        {endpoint.protocol.replace("_", " ").toUpperCase()}
      </span>
      <span className="col-span-6 flex items-center gap-2 md:col-span-2">
        <Badge variant={discovery === "present" ? "positive" : "warning"}>
          {t(`endpoints.discovery.${discovery}`)}
        </Badge>
        {item.retained_by_routes ? (
          <span className="text-xs text-warning">
            {t("endpoints.retained")}
          </span>
        ) : null}
      </span>
      <span className="col-span-6 text-right text-sm text-ink-500 md:col-span-2">
        <span className="mr-1 text-xs text-ink-400 md:hidden">
          {t("endpoints.columns.lastSeen")}
        </span>
        <Time value={item.last_seen_at} />
      </span>
    </li>
  );
}

function ProviderActivity({ provider }: { provider: ProviderRecord }) {
  const t = useTranslations("dashboard.endpointProviders.rowExpansion");
  const [page, setPage] = useState(1);
  const query = useProviderRuns(provider.id, page, EXPANSION_PAGE_SIZE);
  const runs = query.data?.items ?? [];

  useEffect(() => {
    if (query.data && page > query.data.max_page) {
      setPage(Math.max(1, query.data.max_page));
    }
  }, [page, query.data]);

  if (query.isLoading) return <ListSkeleton />;
  if (query.isError) {
    return (
      <InlineError
        title={t("activity.errorTitle")}
        body={t("activity.errorBody")}
        retry={t("retry")}
        onRetry={() => query.refetch()}
      />
    );
  }
  if (!runs.length) {
    return (
      <EmptyState
        title={t("activity.emptyTitle")}
        body={t("activity.emptyBody")}
      />
    );
  }

  return (
    <section
      aria-label={t("activity.listLabel")}
      className="flex min-w-0 flex-col gap-2"
    >
      {query.data && query.data.total > EXPANSION_PAGE_SIZE ? (
        <CompactTablePager
          page={query.data.page}
          maxPage={query.data.max_page}
          pageSize={query.data.size}
          pageItemCount={query.data.items.length}
          total={query.data.total}
          onPageChange={setPage}
          rangeLabel={({ from, to, total }) => t("range", { from, to, total })}
          prevLabel={t("previous")}
          nextLabel={t("next")}
          loading={query.isPlaceholderData}
        />
      ) : null}

      <div
        className="hidden grid-cols-12 gap-x-6 border-b border-table-frame pb-2 text-xs font-medium text-ink-500 md:grid"
        aria-hidden
      >
        <span className="col-span-3">{t("activity.columns.trigger")}</span>
        <span className="col-span-2">{t("activity.columns.status")}</span>
        <span className="col-span-5">{t("activity.columns.changes")}</span>
        <span className="col-span-2 text-right">
          {t("activity.columns.started")}
        </span>
      </div>

      <ol
        aria-busy={query.isPlaceholderData}
        inert={query.isPlaceholderData ? true : undefined}
        className={cn(
          "divide-y divide-table-frame transition-opacity",
          query.isPlaceholderData && "pointer-events-none opacity-60",
        )}
      >
        {runs.map((run) => {
          const working = run.state === "queued" || run.state === "running";
          const failed = run.state === "failed" || run.state === "partial";
          return (
            <li
              key={run.id}
              className="grid grid-cols-12 items-start gap-x-6 gap-y-2 py-3.5 first:pt-1 last:pb-1"
            >
              <span className="col-span-7 flex items-center gap-2 font-semibold text-ink-900 md:col-span-3">
                {working ? (
                  <LoaderCircleIcon
                    className="size-4 animate-spin text-brand"
                    aria-hidden
                  />
                ) : failed ? (
                  <AlertTriangleIcon
                    className="size-4 text-warning"
                    aria-hidden
                  />
                ) : (
                  <CheckCircle2Icon
                    className="size-4 text-positive"
                    aria-hidden
                  />
                )}
                {t(`activity.trigger.${run.trigger}`)}
              </span>
              <span className="col-span-5 flex justify-end md:col-span-2 md:justify-start">
                <Badge
                  variant={working ? "brand" : failed ? "warning" : "positive"}
                >
                  {t(`activity.state.${run.state}`)}
                </Badge>
              </span>
              <span className="col-span-7 text-sm tabular-nums text-ink-500 md:col-span-5">
                {working
                  ? t("activity.inProgress")
                  : run.endpoint_changes > 0
                    ? t("activity.changes", {
                        count: run.endpoint_changes,
                      })
                    : t("activity.noChanges")}
              </span>
              <span className="col-span-5 text-right text-sm text-ink-500 md:col-span-2">
                <Time value={run.started_at ?? run.queued_at} />
              </span>
              {run.error ? (
                <p className="col-span-12 text-sm text-warning md:col-span-9 md:col-start-4">
                  {run.error}
                </p>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function Fact({
  className,
  label,
  mono = false,
  children,
}: {
  className?: string;
  label: string;
  mono?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className={className}>
      <dt className="text-xs font-medium text-ink-500">{label}</dt>
      <dd
        className={`mt-1 break-words text-sm text-ink-900 ${mono ? "font-mono text-xs" : ""}`}
      >
        {children}
      </dd>
    </div>
  );
}

function ListSkeleton() {
  return (
    <div className="space-y-3">
      {["a", "b", "c", "d", "e"].map((key) => (
        <Skeleton key={key} className="h-12 w-full rounded-md" />
      ))}
    </div>
  );
}

function InlineError({
  title,
  body,
  retry,
  onRetry,
}: {
  title: string;
  body: string;
  retry: string;
  onRetry: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-6 rounded-lg bg-danger-soft px-5 py-4">
      <div>
        <p className="text-sm font-semibold text-danger">{title}</p>
        <p className="mt-1 text-sm text-ink-700">{body}</p>
      </div>
      <Button size="sm" variant="soft" onClick={onRetry}>
        {retry}
      </Button>
    </div>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-lg bg-ink-wash px-5 py-4">
      <p className="text-sm font-medium text-ink-900">{title}</p>
      <p className="mt-1 text-sm text-ink-500">{body}</p>
    </div>
  );
}

export { ProviderRowExpansion };
