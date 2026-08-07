"use client";

import {
  EyeIcon,
  EyeOffIcon,
  FileClockIcon,
  MoreHorizontalIcon,
  PencilIcon,
  PowerIcon,
  Trash2Icon,
} from "lucide-react";
import { useTranslations } from "next-intl";

import type { Endpoint } from "@/api/endpoints/client";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

export function EndpointActionsMenu({
  endpoint,
  selected,
  togglePending,
  onSelect,
  onEdit,
  onAudit,
  onToggleEnabled,
  onDelete,
}: {
  endpoint: Endpoint;
  selected: boolean;
  togglePending: boolean;
  onSelect: (id: string) => void;
  onEdit: (endpoint: Endpoint) => void;
  onAudit: (endpoint: Endpoint) => void;
  onToggleEnabled: (endpoint: Endpoint) => void;
  onDelete: (endpoint: Endpoint) => void;
}) {
  const t = useTranslations("dashboard.endpoints");

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={t("actions.openMenu")}
          onClick={(event) => event.stopPropagation()}
          className={cn(
            "inline-flex size-7 items-center justify-center rounded-md text-ink-400 transition-colors",
            "hover:bg-ink-wash hover:text-ink-700",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40",
            "data-[state=open]:bg-ink-wash data-[state=open]:text-ink-900",
          )}
        >
          <MoreHorizontalIcon className="size-4" aria-hidden />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        onClick={(event) => event.stopPropagation()}
      >
        <DropdownMenuItem onSelect={() => onSelect(endpoint.id)}>
          {selected ? <EyeOffIcon aria-hidden /> : <EyeIcon aria-hidden />}
          <span>
            {selected ? t("actions.hideDetails") : t("actions.viewDetails")}
          </span>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => onEdit(endpoint)}>
          <PencilIcon aria-hidden />
          <span>{t("actions.edit")}</span>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => onAudit(endpoint)}>
          <FileClockIcon aria-hidden />
          <span>{t("actions.audit")}</span>
        </DropdownMenuItem>
        <DropdownMenuItem
          disabled={togglePending}
          onSelect={() => onToggleEnabled(endpoint)}
        >
          <PowerIcon aria-hidden />
          <span>
            {endpoint.enabled ? t("actions.disable") : t("actions.enable")}
          </span>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          variant="destructive"
          onSelect={() => onDelete(endpoint)}
        >
          <Trash2Icon aria-hidden />
          <span>{t("actions.delete")}</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
