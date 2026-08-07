"use client";

import { ArrowRight, Trash2Icon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import type { Endpoint } from "@/api/endpoints/client";
import { Button } from "@/components/ui/button";
import { Tabs } from "@/components/ui/tabs";
import { Link, usePathname, useRouter } from "@/i18n/navigation";

import { EndpointsContent } from "./endpoints-content";
import { NewEndpointButton } from "./new-endpoint-button";

export type EndpointsTab = "manual" | "provider";

const PROVIDERS_HREF = "/dashboard/providers";

/**
 * The Endpoints page shell: two tab-switched tables over the Endpoint Registry —
 * "Manual" (self-created, full CRUD) and "Provider" (provider-synced, managed
 * inventory). The page-header CTA follows the active tab: create a manual
 * endpoint, or jump to provider management. The tab row is reserved for the
 * contextual bulk-delete action. Initial tab comes from `?tab=`; switching
 * writes it back so a provider deep-link survives reload.
 *
 * `?provider=<id>` additionally scopes the provider tab to one provider — the
 * hand-off from the provider drawer's "View in Endpoints". Both the scoping
 * chip and a tab switch clear it back out of the URL.
 */
export function EndpointsView({
  initialTab,
  initialProviderId = null,
}: {
  initialTab: EndpointsTab;
  /** Provider to scope the provider tab to, from the `?provider=` deep link. */
  initialProviderId?: string | null;
}) {
  const t = useTranslations("dashboard.endpoints");
  const router = useRouter();
  const pathname = usePathname();

  const [tab, setTab] = useState<EndpointsTab>(initialTab);
  const [providerId, setProviderId] = useState<string | null>(
    initialProviderId,
  );
  const [selectedById, setSelectedById] = useState<Map<string, Endpoint>>(
    () => new Map(),
  );
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);

  const tabOptions = useMemo(
    () => [
      { value: "manual" as const, label: t("tabs.manual") },
      { value: "provider" as const, label: t("tabs.provider") },
    ],
    [t],
  );

  // The provider scope belongs to the provider tab only, so leaving that tab
  // drops it rather than carrying an invisible filter across.
  const changeTab = (next: EndpointsTab) => {
    setTab(next);
    setProviderId(null);
    setSelectedById(new Map());
    setBulkDeleteOpen(false);
    router.replace(next === "provider" ? `${pathname}?tab=provider` : pathname);
  };

  const clearProvider = () => {
    setProviderId(null);
    router.replace(`${pathname}?tab=provider`);
  };

  return (
    <div className="flex flex-col gap-7 pt-2">
      <header className="flex flex-wrap items-end justify-between gap-6">
        <div className="flex max-w-prose-narrow flex-col gap-1.5">
          <h1 className="text-3xl font-bold tracking-tight text-ink-900">
            {t("title")}
          </h1>
          <p className="text-md text-ink-500">{t("subtitle")}</p>
        </div>
        {tab === "manual" ? (
          <NewEndpointButton label={t("cta.newEndpoint")} />
        ) : (
          <Button asChild variant="soft" size="xl" className="group gap-0">
            <Link href={PROVIDERS_HREF}>
              {t("cta.manageProviders")}
              <span
                aria-hidden
                className="inline-flex w-0 shrink-0 overflow-hidden opacity-0 transition-all duration-150 group-hover:ml-2 group-hover:w-4 group-hover:opacity-100 group-focus-visible:ml-2 group-focus-visible:w-4 group-focus-visible:opacity-100 pointer-coarse:ml-2 pointer-coarse:w-4 pointer-coarse:opacity-100"
              >
                <ArrowRight className="size-4 shrink-0 -translate-x-1 transition-transform duration-150 group-hover:translate-x-0 group-focus-visible:translate-x-0 pointer-coarse:translate-x-0" />
              </span>
            </Link>
          </Button>
        )}
      </header>

      <div>
        <div className="flex items-end justify-between gap-4">
          <Tabs
            mode="tab"
            variant="underline"
            size="lg"
            value={tab}
            onChange={changeTab}
            options={tabOptions}
            ariaLabel={t("tabsAriaLabel")}
            idBase="endpoints-tab"
          />
          <div
            data-slot="endpoint-tab-action"
            className="flex w-48 shrink-0 justify-end"
          >
            {tab === "manual" && selectedById.size > 0 ? (
              <Button
                type="button"
                variant="destructive"
                size="sm"
                onClick={() => setBulkDeleteOpen(true)}
              >
                <Trash2Icon aria-hidden />
                {t("bulk.deleteSelectedCount", { count: selectedById.size })}
              </Button>
            ) : null}
          </div>
        </div>
        <div
          id="endpoints-tab-panel"
          role="tabpanel"
          aria-labelledby={`endpoints-tab-${tab}`}
          className="pt-6"
        >
          {tab === "manual" ? (
            <EndpointsContent
              key="manual"
              origin="manual"
              selectedById={selectedById}
              setSelectedById={setSelectedById}
              bulkDeleteOpen={bulkDeleteOpen}
              onBulkDeleteOpenChange={setBulkDeleteOpen}
            />
          ) : (
            <EndpointsContent
              key="provider"
              origin="provider"
              providerId={providerId}
              onClearProvider={clearProvider}
              selectedById={selectedById}
              setSelectedById={setSelectedById}
              bulkDeleteOpen={bulkDeleteOpen}
              onBulkDeleteOpenChange={setBulkDeleteOpen}
            />
          )}
        </div>
      </div>
    </div>
  );
}
