"use client";

import { LoaderCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { type KeyboardEvent, useRef } from "react";
import { Link } from "@/i18n/navigation";
import { cn } from "@/lib/utils";

const ITEMS = [
  { key: "registry", panelId: "endpoint-workspace-registry" },
  { key: "providers", panelId: "endpoint-workspace-providers" },
] as const;

type EndpointWorkspaceView = (typeof ITEMS)[number]["key"];

const TAB_CLASS =
  "relative py-2 text-sm font-semibold text-ink-500 transition-colors hover:text-ink-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40";

export function EndpointWorkspaceNav({
  value,
  onChange,
  activeRuns = 0,
}: {
  value: EndpointWorkspaceView;
  onChange: (value: EndpointWorkspaceView) => void;
  activeRuns?: number;
}) {
  const t = useTranslations("dashboard.endpoints.workspace");
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  function handleKeyDown(
    event: KeyboardEvent<HTMLButtonElement>,
    index: number,
  ) {
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight") nextIndex = (index + 1) % ITEMS.length;
    if (event.key === "ArrowLeft")
      nextIndex = (index - 1 + ITEMS.length) % ITEMS.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = ITEMS.length - 1;
    if (nextIndex === null) return;

    event.preventDefault();
    onChange(ITEMS[nextIndex].key);
    tabRefs.current[nextIndex]?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label={t("label")}
      className="flex items-center gap-6"
    >
      {ITEMS.map((item, index) => {
        const active = value === item.key;
        return (
          <button
            type="button"
            role="tab"
            key={item.key}
            id={`endpoint-workspace-tab-${item.key}`}
            aria-selected={active}
            aria-controls={item.panelId}
            tabIndex={active ? 0 : -1}
            ref={(element) => {
              tabRefs.current[index] = element;
            }}
            onClick={() => onChange(item.key)}
            onKeyDown={(event) => handleKeyDown(event, index)}
            className={cn(
              TAB_CLASS,
              active &&
                "text-ink-900 after:absolute after:right-0 after:bottom-0 after:left-0 after:h-0.5 after:rounded-full after:bg-brand",
            )}
          >
            {t(item.key)}
            {item.key === "providers" && activeRuns > 0 ? (
              <span className="ml-2 inline-flex items-center gap-1 text-xs text-ink-500">
                <LoaderCircle className="size-3 animate-spin" aria-hidden />
                {t("syncRunning", { count: activeRuns })}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

function EndpointWorkspaceLinks({ value }: { value: EndpointWorkspaceView }) {
  const t = useTranslations("dashboard.endpoints.workspace");

  return (
    <nav aria-label={t("label")} className="flex items-center gap-6">
      {ITEMS.map((item) => {
        const active = value === item.key;
        return (
          <Link
            key={item.key}
            href={
              item.key === "providers"
                ? "/dashboard/endpoints?workspace=providers"
                : "/dashboard/endpoints"
            }
            aria-current={active ? "page" : undefined}
            className={cn(
              TAB_CLASS,
              active &&
                "text-ink-900 after:absolute after:right-0 after:bottom-0 after:left-0 after:h-0.5 after:rounded-full after:bg-brand",
            )}
          >
            {t(item.key)}
          </Link>
        );
      })}
    </nav>
  );
}

export { EndpointWorkspaceLinks };
export type { EndpointWorkspaceView };
