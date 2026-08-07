"use client";

import { AlertTriangle } from "lucide-react";
import { useTranslations } from "next-intl";

import { ConfirmDialog } from "@/components/patterns/confirm-dialog";

export type ConfigChangeSummary = {
  label: string;
  before: string;
  after: string;
};

type ConfigChangeConfirmDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  changes: readonly ConfigChangeSummary[];
  onConfirm: () => void;
  impact?: string;
  confirming?: boolean;
};

/**
 * Shared confirmation for high-impact system configuration changes. It makes
 * the exact before/after values reviewable without prescribing which form
 * owns the draft or mutation.
 */
export function ConfigChangeConfirmDialog({
  open,
  onOpenChange,
  changes,
  onConfirm,
  impact,
  confirming = false,
}: ConfigChangeConfirmDialogProps) {
  const t = useTranslations("dashboard.settings.configShared.riskConfirm");

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("title")}
      description={t("description")}
      icon={<AlertTriangle aria-hidden />}
      onConfirm={onConfirm}
      confirmLabel={t("confirm")}
      confirmingLabel={t("confirming")}
      cancelLabel={t("cancel")}
      confirming={confirming}
      destructive={false}
      contentClassName="max-h-[calc(100dvh-2rem)] overflow-hidden"
    >
      <div className="min-h-0 overflow-y-auto rounded-xl border border-border">
        <dl className="divide-y divide-border">
          {changes.map((change) => (
            <div
              key={change.label}
              className="grid gap-2 px-4 py-3 text-sm sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]"
            >
              <dt className="font-medium text-ink-700">{change.label}</dt>
              <dd className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 tabular-nums text-ink-900">
                <span className="min-w-0 break-words text-ink-500">
                  {change.before}
                </span>
                <span aria-hidden className="text-ink-400">
                  →
                </span>
                <span className="min-w-0 break-words font-medium">
                  {change.after}
                </span>
              </dd>
            </div>
          ))}
        </dl>
      </div>
      {impact ? (
        <p className="rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning">
          <span className="font-semibold">{t("impact")}: </span>
          {impact}
        </p>
      ) : null}
    </ConfirmDialog>
  );
}
