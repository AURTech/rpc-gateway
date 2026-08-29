"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { listProviders, type RpcProviderBase } from "@/api/providers/client";
import { cn } from "@/lib/utils";

import { NewProviderButton } from "../../../providers/_components/new-provider-button";

const PAGE_SIZE = 100;
const PROVIDER_VIEWPORT_ROWS = 10;
const PROVIDER_FILLER_KEYS = [
  "provider-filler-1",
  "provider-filler-2",
  "provider-filler-3",
  "provider-filler-4",
  "provider-filler-5",
  "provider-filler-6",
  "provider-filler-7",
  "provider-filler-8",
  "provider-filler-9",
  "provider-filler-10",
] as const;

async function listAllEnabledProviders(): Promise<RpcProviderBase[]> {
  const first = await listProviders({
    enabled: true,
    page: 1,
    size: PAGE_SIZE,
  });
  const items = [...first.items];
  for (let page = 2; page <= first.max_page; page += 1) {
    const result = await listProviders({
      enabled: true,
      page,
      size: PAGE_SIZE,
    });
    items.push(...result.items);
  }
  return items;
}

/**
 * Final wizard step: pick the Provider whose synchronized Endpoints get wired
 * to the new App's Gateways.
 *
 * Creating a Provider is delegated to the account-wide {@link NewProviderButton}
 * dialog rather than re-implemented inline: a Provider is an account resource,
 * not an App-scoped draft, so it is written immediately and simply lands in the
 * picker — selected — via `onCreated`. Leaving the wizard afterwards still
 * creates no App, and the Provider stays usable from the Providers page.
 */
export function RpcAccessStep({
  value,
  onChange,
  disabled,
  footer,
}: {
  /** Selected provider id, or `""` when the step is left empty. */
  value: string;
  onChange: (providerId: string) => void;
  disabled: boolean;
  footer?: ReactNode;
}) {
  const t = useTranslations("dashboard.apps.wizard.rpcAccess");
  const providerVendor = useTranslations(
    "dashboard.endpointProviders.onboarding.vendors",
  );
  const providersQuery = useQuery({
    queryKey: ["providers", "create-app", "enabled"],
    queryFn: listAllEnabledProviders,
    staleTime: 15_000,
  });

  const providers = providersQuery.data ?? [];
  const isEmpty = providersQuery.isSuccess && providers.length === 0;

  return (
    <section
      data-slot="provider-selection"
      className="overflow-hidden rounded-3xl bg-table-frame shadow-elevated"
    >
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 px-4 py-3">
        <div className="min-w-0 flex-1 basis-64">
          <h2 className="text-sm font-semibold text-ink-900">
            {t("provider.title")}
          </h2>
          <p className="mt-0.5 text-2xs leading-snug text-ink-500">
            {t("provider.subtitle")}
          </p>
        </div>
        <NewProviderButton
          label={t("provider.createNew")}
          size="sm"
          variant="soft"
          showIcon={false}
          className="rounded-xl"
          disabled={disabled}
          onCreated={(provider) => onChange(provider.id)}
        />
      </header>

      <div
        data-slot="provider-selection-table"
        className="mx-1 overflow-hidden rounded-table-pill bg-surface"
      >
        <div
          data-slot="provider-selection-table-scroll"
          className="h-table-viewport overflow-auto"
        >
          <table
            aria-label={t("provider.title")}
            className="w-full min-h-full table-fixed border-collapse"
          >
            <colgroup>
              <col />
              <col className="w-40" />
              <col className="w-40" />
              <col className="w-24" />
            </colgroup>
            <thead className="sticky top-0 z-10 border-b border-ink-wash bg-surface">
              <tr>
                <th className="h-table-head px-4 text-left text-xs font-medium text-ink-500">
                  {t("provider.columns.provider")}
                </th>
                <th className="h-table-head px-4 text-left text-xs font-medium text-ink-500">
                  {t("provider.columns.vendor")}
                </th>
                <th className="h-table-head px-4 text-left text-xs font-medium text-ink-500">
                  {t("provider.columns.networks")}
                </th>
                <th className="h-table-head px-4 text-right text-xs font-medium text-ink-500">
                  {t("provider.columns.select")}
                </th>
              </tr>
            </thead>
            <tbody>
              {providersQuery.isLoading ? (
                <tr className="h-full">
                  <td
                    colSpan={4}
                    className="h-full px-4 text-center text-sm text-ink-400"
                  >
                    {t("provider.loading")}
                  </td>
                </tr>
              ) : providersQuery.isError ? (
                <tr className="h-full">
                  <td
                    colSpan={4}
                    className="h-full px-4 text-center text-sm text-danger"
                  >
                    {t("provider.loadError")}
                  </td>
                </tr>
              ) : isEmpty ? (
                <tr className="h-full">
                  <td colSpan={4} className="h-full px-4">
                    <div className="mx-auto flex h-full max-w-prose-narrow flex-col items-center justify-center gap-2 text-center">
                      <span className="text-lg font-semibold text-ink-900">
                        {t("provider.emptyTitle")}
                      </span>
                      <span className="text-sm text-ink-500">
                        {t("provider.empty")}
                      </span>
                      <NewProviderButton
                        label={t("provider.emptyCta")}
                        size="sm"
                        className="mt-2"
                        disabled={disabled}
                        onCreated={(provider) => onChange(provider.id)}
                      />
                    </div>
                  </td>
                </tr>
              ) : (
                <>
                  {providers.map((provider) => {
                    const selected = provider.id === value;
                    const inputId = `app-provider-${provider.id}`;
                    return (
                      <tr
                        key={provider.id}
                        className={cn(
                          "transition-colors",
                          selected ? "bg-brand-soft" : "hover:bg-row-hover",
                        )}
                      >
                        <td className="h-table-row min-w-0 px-4 align-middle">
                          <label
                            htmlFor={inputId}
                            className="block cursor-pointer truncate text-sm font-semibold text-ink-900"
                          >
                            {provider.name}
                          </label>
                        </td>
                        <td className="h-table-row px-4 align-middle text-sm text-ink-500">
                          {providerVendor(provider.vendor)}
                        </td>
                        <td className="h-table-row px-4 align-middle text-sm text-ink-500">
                          {provider.networks
                            ? t("provider.networkCount", {
                                count: provider.networks.length,
                              })
                            : t("provider.allNetworks")}
                        </td>
                        <td className="h-table-row px-4 align-middle">
                          <div className="flex justify-end">
                            <input
                              id={inputId}
                              type="radio"
                              name="app-provider"
                              value={provider.id}
                              checked={selected}
                              disabled={disabled}
                              onChange={() => onChange(provider.id)}
                              aria-label={t("provider.selectLabel", {
                                name: provider.name,
                              })}
                              className="size-4 cursor-pointer accent-brand disabled:cursor-not-allowed disabled:opacity-60"
                            />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  {PROVIDER_FILLER_KEYS.slice(
                    0,
                    Math.max(0, PROVIDER_VIEWPORT_ROWS - providers.length),
                  ).map((key) => (
                    <tr key={key}>
                      <td className="h-table-row bg-surface" colSpan={4} />
                    </tr>
                  ))}
                </>
              )}
            </tbody>
          </table>
        </div>
      </div>
      {footer ? (
        <footer data-slot="provider-selection-actions" className="px-4 py-3">
          {footer}
        </footer>
      ) : null}
    </section>
  );
}
