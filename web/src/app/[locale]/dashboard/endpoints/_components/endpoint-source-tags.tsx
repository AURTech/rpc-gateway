"use client";

import { useTranslations } from "next-intl";

import type { Endpoint } from "@/api/endpoints/client";
import { Badge } from "@/components/ui/badge";
import { Link } from "@/i18n/navigation";
import { cn } from "@/lib/utils";

/**
 * Origin display for an endpoint, shared by the desktop row and the detail
 * sheet. Manual endpoints show a neutral origin badge; provider-synced
 * endpoints show the vendor as a chip linking to the provider, plus a
 * sync-status dot (available vs. missing on the last sync). Mirrors the Nodes
 * page's source tags, adapted to the v2 Endpoint provider fields.
 */
export function EndpointSourceTags({
  endpoint,
  className,
}: {
  endpoint: Pick<Endpoint, "origin_type" | "provider" | "provider_sync_status">;
  className?: string;
}) {
  const t = useTranslations("dashboard.endpoints");

  if (endpoint.origin_type === "provider" && endpoint.provider) {
    const missing = endpoint.provider_sync_status === "missing";
    return (
      <span className={cn("inline-flex items-center gap-1.5", className)}>
        <Link
          href={`/dashboard/providers?provider=${endpoint.provider.id}`}
          onClick={(event) => event.stopPropagation()}
          className="inline-flex items-center gap-1.5 rounded-full bg-ink-wash px-2 py-0.5 text-xs font-medium text-ink-700 transition-colors hover:bg-stripe hover:text-brand"
        >
          {endpoint.provider_sync_status ? (
            <span
              aria-hidden
              className={cn(
                "size-1.5 shrink-0 rounded-full",
                missing ? "bg-danger" : "bg-positive",
              )}
            />
          ) : null}
          {endpoint.provider.vendor_label}
        </Link>
        {endpoint.provider_sync_status ? (
          <span className="sr-only">
            {t(`sync.${endpoint.provider_sync_status}`)}
          </span>
        ) : null}
      </span>
    );
  }

  return (
    <Badge variant="neutral" className={className}>
      {t(`origin.${endpoint.origin_type}`)}
    </Badge>
  );
}
