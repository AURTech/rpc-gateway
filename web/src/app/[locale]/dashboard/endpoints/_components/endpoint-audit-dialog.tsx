"use client";

import { useTranslations } from "next-intl";

import type { Endpoint } from "@/api/endpoints/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Time } from "@/components/ui/time";
import { useEndpointAuditQuery } from "@/hooks/use-endpoints";

export function EndpointAuditDialog({
  endpoint,
  open,
  onOpenChange,
}: {
  endpoint: Endpoint | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("dashboard.endpoints");
  const query = useEndpointAuditQuery(open ? (endpoint?.id ?? null) : null);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-screen overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {t("audit.title", { name: endpoint?.name ?? "" })}
          </DialogTitle>
          <DialogDescription>{t("audit.description")}</DialogDescription>
        </DialogHeader>
        {query.isPending ? (
          <p className="py-8 text-center text-sm text-ink-500">
            {t("loading")}
          </p>
        ) : query.isError ? (
          <div className="flex flex-col items-center gap-3 py-8">
            <p className="text-sm text-danger">{t("audit.loadError")}</p>
            <Button
              type="button"
              variant="outline"
              onClick={() => query.refetch()}
            >
              {t("retry")}
            </Button>
          </div>
        ) : query.data?.items.length ? (
          <ol className="flex flex-col gap-3">
            {query.data.items.map((event) => (
              <li
                key={event.id}
                className="rounded-lg border border-ink-100 p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Badge variant="neutral">
                    {t(`audit.action.${event.action}`)}
                  </Badge>
                  <Time
                    value={event.created_at}
                    className="text-xs text-ink-500"
                  />
                </div>
                <p className="mt-2 text-sm text-ink-700">
                  {t("audit.version", {
                    previous: event.previous_version ?? "—",
                    next: event.new_version,
                  })}
                </p>
                <p className="mt-1 text-xs text-ink-500">
                  {event.changed_fields.length
                    ? t("audit.fields", {
                        fields: event.changed_fields.join(", "),
                      })
                    : t("audit.noFields")}
                </p>
              </li>
            ))}
          </ol>
        ) : (
          <p className="py-8 text-center text-sm text-ink-500">
            {t("audit.empty")}
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
