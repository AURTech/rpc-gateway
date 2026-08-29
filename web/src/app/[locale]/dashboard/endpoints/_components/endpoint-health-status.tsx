"use client";

import { useTranslations } from "next-intl";

import type { EndpointHealth } from "@/api/endpoints/client";
import { Badge } from "@/components/ui/badge";

export function EndpointHealthStatus({
  health,
}: {
  health: EndpointHealth | null;
}) {
  const t = useTranslations("dashboard.endpoints.health.status");
  const status = health?.status;

  if (!status || status === "unknown") {
    return (
      <span className="text-sm text-ink-400" title={t("noRecentData")}>
        <span aria-hidden>—</span>
        <span className="sr-only">{t("noRecentData")}</span>
      </span>
    );
  }

  return (
    <Badge variant={status === "healthy" ? "positive" : "danger"}>
      {t(status)}
    </Badge>
  );
}
