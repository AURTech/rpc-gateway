"use client";

import {
  Building2,
  FolderOpen,
  Globe,
  Layers,
  type LucideIcon,
  RefreshCw,
  Tag,
} from "lucide-react";
import { useTranslations } from "next-intl";

import type { RpcProviderBase } from "@/api/providers/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Time } from "@/components/ui/time";
import { cn } from "@/lib/utils";

import { VendorCover, VendorLogo } from "./provider-brand";
import { type ProviderMetaKey, readProviderMeta } from "./provider-meta";
import { SyncStatusPill } from "./provider-pills";
import { useProviderSync } from "./use-provider-actions";

const META_ICONS: Record<ProviderMetaKey, LucideIcon> = {
  type: Layers,
  project: FolderOpen,
  organization: Building2,
  region: Globe,
};

const MAX_TAGS = 3;

/** A single metadata chip: leading category icon + operator-supplied value. */
function MetaChip({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
}) {
  return (
    <Badge
      variant="neutral"
      className="max-w-full gap-1"
      title={`${label}: ${value}`}
    >
      <Icon className="size-3 shrink-0 text-ink-400" aria-hidden />
      <span className="truncate">{value}</span>
    </Badge>
  );
}

/**
 * A provider card in the {@link CardGridView} grid: a banner-style panel. A
 * brand cover tops the card with the vendor's circular logo straddling its
 * bottom-left; the body carries the name, operator-supplied metadata chips, and
 * a compact status row with a single overflow actions menu. Tapping the card
 * (anywhere but the sync button) opens the provider detail drawer beside the
 * grid — there is no detail page to navigate to.
 */
export function ProviderCard({
  provider,
  onOpen,
}: {
  provider: RpcProviderBase;
  /** Opens the detail drawer for this provider. */
  onOpen: (id: string) => void;
}) {
  const t = useTranslations("dashboard.providers");
  const sync = useProviderSync(provider);
  const openDetail = () => onOpen(provider.id);

  const meta = readProviderMeta(provider);
  const hasMeta = meta.fields.length > 0 || meta.tags.length > 0;
  const shownTags = meta.tags.slice(0, MAX_TAGS);
  const extraTags = meta.tags.length - shownTags.length;
  return (
    <>
      {/* biome-ignore lint/a11y/useSemanticElements: a native <button> can't wrap the card's nested interactive controls (actions menu); div+role=button with a keyboard handler mirrors the shared DataCard pattern. */}
      <div
        role="button"
        tabIndex={0}
        aria-label={t("actions.viewDetails")}
        onClick={openDetail}
        onKeyDown={(e) => {
          if (e.target !== e.currentTarget) return;
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            openDetail();
          }
        }}
        className={cn(
          "group flex cursor-pointer flex-col overflow-hidden rounded-2xl bg-surface shadow-card transition-shadow",
          "hover:shadow-section focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand/40",
        )}
      >
        {/* Cover banner with the logo straddling its bottom-left edge. */}
        <div className="relative">
          <VendorCover
            vendor={provider.vendor}
            className={cn(
              "w-full",
              !provider.enabled && "opacity-60 grayscale",
            )}
            style={{ aspectRatio: "16 / 6" }}
          />
          <VendorLogo
            vendor={provider.vendor}
            label={provider.vendor_label}
            className={cn(
              "absolute left-4 top-full size-14 -translate-y-1/2 shrink-0 shadow-card ring-2 ring-surface",
              !provider.enabled && "opacity-60 grayscale",
            )}
          />
        </div>

        <div className="flex flex-col gap-3 p-4 pt-9">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <span className="block truncate text-md font-semibold text-ink-900">
                {provider.name}
              </span>
              <span className="block truncate text-sm text-ink-500">
                {provider.vendor_label}
              </span>
            </div>
            <SyncStatusPill
              status={provider.last_sync_status}
              label={provider.last_sync_status_label}
            />
          </div>

          {hasMeta ? (
            <div className="flex flex-wrap gap-1.5">
              {meta.fields.map((field) => (
                <MetaChip
                  key={field.key}
                  icon={META_ICONS[field.key]}
                  label={t(`card.meta.${field.key}`)}
                  value={field.value}
                />
              ))}
              {shownTags.map((tag) => (
                <MetaChip
                  key={`tag:${tag}`}
                  icon={Tag}
                  label={t("card.meta.tags")}
                  value={tag}
                />
              ))}
              {extraTags > 0 ? (
                <Badge variant="neutral">
                  {t("card.tagsMore", { count: extraTags })}
                </Badge>
              ) : null}
            </div>
          ) : null}

          <div className="flex items-center justify-between gap-3 border-t border-table-frame pt-3">
            <div className="flex min-w-0 items-center gap-2 text-xs text-ink-500">
              <span
                aria-hidden
                className={cn(
                  "size-1.5 shrink-0 rounded-full",
                  provider.enabled ? "bg-positive" : "bg-ink-400",
                )}
              />
              <span className="truncate">
                {sync.syncPending ? (
                  <span className="inline-flex items-center gap-1.5 text-brand">
                    <RefreshCw className="size-3 animate-spin" aria-hidden />
                    {t("actions.syncing")}
                  </span>
                ) : provider.last_sync_at ? (
                  <Time value={provider.last_sync_at} />
                ) : (
                  t("card.neverSynced")
                )}
              </span>
              <span aria-hidden>·</span>
              <span className="shrink-0">
                {provider.sync_enabled
                  ? t("detail.dailyAutomatic")
                  : t("detail.manualOnly")}
              </span>
            </div>
            <Button
              type="button"
              variant="outline"
              size="icon-sm"
              disabled={sync.syncPending}
              aria-label={
                sync.syncPending ? t("actions.syncing") : t("actions.syncNow")
              }
              title={
                sync.syncPending ? t("actions.syncing") : t("actions.syncNow")
              }
              onClick={(e) => {
                e.stopPropagation();
                sync.runSync();
              }}
            >
              <RefreshCw
                className={cn(sync.syncPending && "animate-spin")}
                aria-hidden
              />
            </Button>
          </div>
        </div>
      </div>

      {sync.syncResultDialog}
    </>
  );
}
