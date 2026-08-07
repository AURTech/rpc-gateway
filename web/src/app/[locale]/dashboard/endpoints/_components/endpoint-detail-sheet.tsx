"use client";

import { FileClockIcon, PencilIcon, Trash2Icon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRef } from "react";
import type { Endpoint, EndpointDetail } from "@/api/endpoints/client";
import { Button } from "@/components/ui/button";
import { ChainIcon } from "@/components/ui/chain-icon";
import { Sheet, SheetShell } from "@/components/ui/sheet";
import { Time } from "@/components/ui/time";
import { useEndpointQuery } from "@/hooks/use-endpoints";

import {
  DetailRow,
  DetailSection,
  Mono,
} from "../../_components/compact-drawer";
import { EndpointSourceTags } from "./endpoint-source-tags";

function DetailBody({ endpoint }: { endpoint: EndpointDetail }) {
  const t = useTranslations("dashboard.endpoints");

  const authParts = [
    endpoint.auth.type === "header_api_key" ? endpoint.auth.header_name : null,
    endpoint.auth.type === "query_api_key" ? endpoint.auth.query_param : null,
    endpoint.auth.type !== "none" ? endpoint.auth.secret : null,
  ].filter((value): value is string => Boolean(value));

  return (
    <div className="flex flex-col gap-6">
      <DetailSection>
        <DetailRow label={t("detail.id")}>
          <Mono className="truncate">{endpoint.id}</Mono>
        </DetailRow>
        <DetailRow label={t("detail.chain")}>
          <span className="inline-flex items-center gap-2 text-md font-medium text-ink-900">
            <ChainIcon
              chain={endpoint.chain}
              network={endpoint.network}
              className="size-4"
            />
            {t(`chain.${endpoint.chain}`)}
          </span>
        </DetailRow>
        <DetailRow label={t("detail.network")}>
          <span className="text-md text-ink-700">
            {t(`network.${endpoint.network}`)}
          </span>
        </DetailRow>
        <DetailRow label={t("detail.protocol")}>
          <span className="text-md text-ink-700">
            {t(`protocol.${endpoint.protocol}`)}
          </span>
        </DetailRow>
        <DetailRow label={t("detail.origin")}>
          <EndpointSourceTags endpoint={endpoint} />
        </DetailRow>
        <DetailRow label={t("detail.enabled")}>
          <span className="text-md text-ink-700">
            {endpoint.enabled ? t("detail.yes") : t("detail.no")}
          </span>
        </DetailRow>
      </DetailSection>

      {endpoint.origin_type === "provider" && endpoint.provider ? (
        <DetailSection title={t("detail.providerSection")}>
          <DetailRow label={t("detail.provider")}>
            <span className="text-md text-ink-700">
              {endpoint.provider.name}
            </span>
          </DetailRow>
          {endpoint.provider_sync_status ? (
            <DetailRow label={t("detail.syncStatus")}>
              <span className="text-md text-ink-700">
                {t(`sync.${endpoint.provider_sync_status}`)}
              </span>
            </DetailRow>
          ) : null}
          {endpoint.provider_last_seen_at ? (
            <DetailRow label={t("detail.lastSeen")}>
              <Time value={endpoint.provider_last_seen_at} mono />
            </DetailRow>
          ) : null}
        </DetailSection>
      ) : null}

      <DetailSection title={t("detail.connection")}>
        <div className="px-1 py-1.5">
          <p className="font-mono text-2xs break-all text-ink-700">
            {endpoint.url}
          </p>
        </div>
        <DetailRow label={t("detail.authType")}>
          <span className="text-md text-ink-700">
            {t(`auth.${endpoint.auth.type}`)}
          </span>
        </DetailRow>
        <DetailRow label={t("detail.authConfig")}>
          <Mono className="truncate">{authParts.join(" · ") || "—"}</Mono>
        </DetailRow>
      </DetailSection>

      <DetailSection>
        <DetailRow label={t("detail.created")}>
          <Time value={endpoint.created_at} mono />
        </DetailRow>
        <DetailRow label={t("detail.modified")}>
          <Time value={endpoint.modified_at} mono />
        </DetailRow>
      </DetailSection>
    </div>
  );
}

export function EndpointDetailSheet({
  endpoint,
  open,
  onOpenChange,
  onEdit,
  onAudit,
  onDelete,
}: {
  endpoint: Endpoint | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onEdit: (endpoint: Endpoint) => void;
  onAudit: (endpoint: Endpoint) => void;
  onDelete: (endpoint: Endpoint) => void;
}) {
  const t = useTranslations("dashboard.endpoints");
  const shownRef = useRef<Endpoint | null>(endpoint);
  if (endpoint) shownRef.current = endpoint;
  const active = endpoint ?? shownRef.current;
  const query = useEndpointQuery(open ? (active?.id ?? null) : null);
  // The list item already carries the full record; prefer the freshest fetch
  // but fall back to the row's data so the sheet never blanks.
  const detail = query.data ?? active;
  const footer = detail ? (
    <div className="flex items-center justify-end gap-2">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={() => onAudit(detail)}
      >
        <FileClockIcon aria-hidden />
        {t("actions.audit")}
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onEdit(detail)}
      >
        <PencilIcon aria-hidden />
        {t("actions.edit")}
      </Button>
      <Button
        type="button"
        variant="destructive"
        size="sm"
        onClick={() => onDelete(detail)}
      >
        <Trash2Icon aria-hidden />
        {t("actions.delete")}
      </Button>
    </div>
  ) : null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetShell
        side="right"
        title={detail?.name ?? t("detail.title")}
        description={
          detail
            ? `${t(`chain.${detail.chain}`)} · ${t(`network.${detail.network}`)}`
            : undefined
        }
        closeButton
        closeLabel={t("actions.hideDetails")}
        footer={footer}
        contentClassName="w-full sm:max-w-lg"
      >
        {query.data ? (
          <DetailBody endpoint={query.data} />
        ) : (
          <p className="py-8 text-center text-sm text-ink-500">
            {t("loading")}
          </p>
        )}
      </SheetShell>
    </Sheet>
  );
}
