"use client";

import {
  Ban,
  EyeIcon,
  EyeOffIcon,
  MoreHorizontalIcon,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import type { AccountBase } from "@/api/accounts/client";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

import { ArchiveConfirmDialog } from "./archive-confirm-dialog";
import { StatusConfirmDialog } from "./status-confirm-dialog";

/**
 * Action menu shared by the desktop table row and the mobile card. Owns the
 * confirm-dialog state for enable / disable / archive, plus the "View details"
 * toggle that drives the side-Sheet detail.
 */
export function AccountRowActions({
  account,
  selected,
  onSelect,
}: {
  account: AccountBase;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  const t = useTranslations("dashboard.admin.accounts");
  const [enableOpen, setEnableOpen] = useState(false);
  const [disableOpen, setDisableOpen] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);

  // Archived accounts never appear in the list, so only the active/disabled
  // pair can be flipped here.
  const canActivate = account.status === "disabled";
  const canDisable = account.status !== "disabled";

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            aria-label={t("actions.openMenu")}
            onClick={(e) => e.stopPropagation()}
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
        <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
          <DropdownMenuItem onSelect={() => onSelect(account.id)}>
            {selected ? <EyeOffIcon aria-hidden /> : <EyeIcon aria-hidden />}
            <span>
              {selected ? t("actions.hideDetails") : t("actions.viewDetails")}
            </span>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          {canActivate ? (
            <DropdownMenuItem onSelect={() => setEnableOpen(true)}>
              <ShieldCheck aria-hidden />
              <span>{t("actions.enable")}</span>
            </DropdownMenuItem>
          ) : null}
          {canDisable ? (
            <DropdownMenuItem
              variant="destructive"
              onSelect={() => setDisableOpen(true)}
            >
              <Ban aria-hidden />
              <span>
                {account.activated ? t("actions.disable") : t("actions.revoke")}
              </span>
            </DropdownMenuItem>
          ) : null}
          <DropdownMenuItem
            variant="destructive"
            onSelect={() => setArchiveOpen(true)}
          >
            <Trash2 aria-hidden />
            <span>{t("actions.archive")}</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <StatusConfirmDialog
        account={account}
        activate
        open={enableOpen}
        onOpenChange={setEnableOpen}
      />
      <StatusConfirmDialog
        account={account}
        activate={false}
        open={disableOpen}
        onOpenChange={setDisableOpen}
      />
      <ArchiveConfirmDialog
        account={account}
        open={archiveOpen}
        onOpenChange={setArchiveOpen}
      />
    </>
  );
}
