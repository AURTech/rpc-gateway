"use client";

import { useTranslations } from "next-intl";

import type { AccountBase } from "@/api/accounts/client";
import { DataCard } from "@/components/patterns/data-card";

import { AccountRowActions } from "./account-row-actions";
import { AccountStatusPill } from "./account-status-pill";

export function AccountCard({
  account,
  selected,
  onSelect,
}: {
  account: AccountBase;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  const t = useTranslations("dashboard.admin.accounts");

  return (
    <DataCard
      title={
        <span className="truncate text-md font-semibold text-ink-900">
          {account.email}
        </span>
      }
      meta={
        <span className="truncate">
          {account.name ? `${account.name} · ` : ""}
          {account.role_label}
        </span>
      }
      trailing={
        <AccountStatusPill
          status={account.status}
          label={account.status_label}
        />
      }
      actions={
        <AccountRowActions
          account={account}
          selected={selected}
          onSelect={onSelect}
        />
      }
      onClick={() => onSelect(account.id)}
      selected={selected}
      ariaLabel={t("actions.viewDetails")}
    />
  );
}
