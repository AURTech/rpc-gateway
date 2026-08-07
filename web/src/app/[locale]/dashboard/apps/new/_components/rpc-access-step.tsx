"use client";

import { useQuery } from "@tanstack/react-query";
import { Server } from "lucide-react";
import { useTranslations } from "next-intl";

import { listProviders, type RpcProviderBase } from "@/api/providers/client";
import { Field } from "@/components/patterns/form-field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { NewProviderButton } from "../../../providers/_components/new-provider-button";

const PAGE_SIZE = 100;

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
}: {
  /** Selected provider id, or `""` when the step is left empty. */
  value: string;
  onChange: (providerId: string) => void;
  disabled: boolean;
}) {
  const t = useTranslations("dashboard.apps.wizard.rpcAccess");
  const providersQuery = useQuery({
    queryKey: ["providers", "create-app", "enabled"],
    queryFn: listAllEnabledProviders,
    staleTime: 15_000,
  });

  const providers = providersQuery.data ?? [];
  const isEmpty = providersQuery.isSuccess && providers.length === 0;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h2 className="text-lg font-semibold text-ink-900">{t("title")}</h2>
        <p className="text-sm text-ink-500">{t("subtitle")}</p>
      </div>

      <section className="overflow-hidden rounded-2xl bg-surface shadow-section">
        <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3 border-b border-ink-wash px-5 py-4">
          <div className="min-w-0 flex-1 basis-64">
            <h3 className="flex items-center gap-2 text-md font-semibold text-ink-900">
              <Server className="size-4" aria-hidden />
              {t("provider.title")}
            </h3>
            <p className="mt-1 text-sm text-ink-500">
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

        <div className="px-5 py-5">
          {providersQuery.isError ? (
            <p className="text-sm text-danger">{t("provider.loadError")}</p>
          ) : isEmpty ? (
            <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-ink-wash px-6 py-10 text-center">
              <p className="text-md font-semibold text-ink-900">
                {t("provider.emptyTitle")}
              </p>
              <p className="max-w-prose-narrow text-sm text-ink-500">
                {t("provider.empty")}
              </p>
              <NewProviderButton
                label={t("provider.emptyCta")}
                size="sm"
                className="mt-2"
                disabled={disabled}
                onCreated={(provider) => onChange(provider.id)}
              />
            </div>
          ) : (
            <Field
              label={t("provider.existingLabel")}
              htmlFor="app-existing-provider"
              hint={t("provider.existingHint")}
            >
              <Select
                value={value}
                disabled={disabled || providersQuery.isLoading}
                onValueChange={onChange}
              >
                <SelectTrigger id="app-existing-provider">
                  <SelectValue
                    placeholder={
                      providersQuery.isLoading
                        ? t("provider.loading")
                        : t("provider.selectPlaceholder")
                    }
                  />
                </SelectTrigger>
                <SelectContent>
                  {providers.map((provider) => (
                    <SelectItem key={provider.id} value={provider.id}>
                      {provider.name} · {provider.vendor_label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          )}
        </div>
      </section>
    </div>
  );
}
