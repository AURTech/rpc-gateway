"use client";

import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { usePathname, useRouter } from "@/i18n/navigation";
import { ConnectProviderButton } from "../providers/_components/connect-provider-button";
import { ProvidersTable } from "../providers/_components/providers-table";
import { EndpointRegistry } from "./endpoint-registry";
import {
  EndpointWorkspaceNav,
  type EndpointWorkspaceView,
} from "./endpoint-workspace-nav";
import { NewEndpointButton } from "./new-endpoint-button";

function EndpointManagementWorkspace({
  initialView = "registry",
}: {
  initialView?: EndpointWorkspaceView;
}) {
  const t = useTranslations("dashboard.endpoints");
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspace = searchParams.get("workspace");
  const view: EndpointWorkspaceView =
    workspace === "providers"
      ? "providers"
      : workspace === "registry"
        ? "registry"
        : initialView;
  const [activeProviderRuns, setActiveProviderRuns] = useState(0);

  function changeView(next: EndpointWorkspaceView) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("workspace", next);
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, {
      scroll: false,
    });
  }

  return (
    <div className="flex min-w-0 flex-col gap-7 pt-2">
      <div className="flex flex-col gap-3">
        <header className="flex max-w-prose-narrow flex-col gap-1.5">
          <h1 className="text-3xl font-bold tracking-tight text-ink-900">
            {t("registry.title")}
          </h1>
          <p className="whitespace-nowrap text-md text-ink-500">
            {t("registry.subtitle")}
          </p>
        </header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <EndpointWorkspaceNav
            value={view}
            onChange={changeView}
            activeRuns={activeProviderRuns}
          />
          <div className="flex shrink-0 items-center gap-2">
            <ConnectProviderButton
              label={t("registry.connectProvider")}
              variant="soft"
            />
            <NewEndpointButton
              label={t("registry.addEndpoint")}
              size="default"
            />
          </div>
        </div>
      </div>

      {view === "registry" ? (
        <div
          id="endpoint-workspace-registry"
          role="tabpanel"
          aria-labelledby="endpoint-workspace-tab-registry"
        >
          <EndpointRegistry />
        </div>
      ) : (
        <div
          id="endpoint-workspace-providers"
          role="tabpanel"
          aria-labelledby="endpoint-workspace-tab-providers"
        >
          <ProvidersTable onActiveRunsChange={setActiveProviderRuns} />
        </div>
      )}
    </div>
  );
}

export { EndpointManagementWorkspace };
