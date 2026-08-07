"use client";

import { CopyIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRef } from "react";
import { toast } from "sonner";

import type { AccountBase } from "@/api/accounts/client";
import { DetailDrawer } from "@/components/patterns/detail-drawer";
import { Skeleton } from "@/components/ui/skeleton";
import { Time } from "@/components/ui/time";
import { useAccountQuery } from "@/hooks/use-accounts";
import { copyToClipboard } from "@/lib/clipboard";

import {
  DetailRow,
  DetailSection,
  IconButton,
  Mono,
} from "../../_components/compact-drawer";
import { AccountStatusPill } from "./account-status-pill";

/**
 * Account detail body. The list row carries the base fields; login activity and
 * resource counts (gateways / apps) fill in once {@link useAccountQuery}
 * resolves the detail endpoint.
 */
function AccountDetailBody({ account }: { account: AccountBase }) {
  const t = useTranslations("dashboard.admin.accounts");
  const detailQuery = useAccountQuery(account.id);
  const detail = detailQuery.data;

  const handleCopy = async (text: string) => {
    const ok = await copyToClipboard(text);
    if (ok) toast.success(t("toast.copyOk"));
    else toast.error(t("toast.copyError"));
  };

  return (
    <div className="flex flex-col gap-6">
      {/* All scalar fields flow as one continuous section; the user agent parks
       * in its own region below. */}
      <DetailSection>
        <DetailRow label={t("detail.email")}>
          <Mono className="truncate">{account.email}</Mono>
          <IconButton
            ariaLabel={t("detail.copyEmail")}
            onClick={() => handleCopy(account.email)}
          >
            <CopyIcon className="size-3.5" aria-hidden />
          </IconButton>
        </DetailRow>
        <DetailRow label={t("detail.userId")}>
          <Mono className="truncate">{account.id}</Mono>
          <IconButton
            ariaLabel={t("detail.copyId")}
            onClick={() => handleCopy(account.id)}
          >
            <CopyIcon className="size-3.5" aria-hidden />
          </IconButton>
        </DetailRow>
        <DetailRow label={t("detail.name")}>
          <span className="truncate text-md font-medium text-ink-900">
            {account.name?.trim() || "—"}
          </span>
        </DetailRow>
        <DetailRow label={t("detail.role")}>
          <span className="text-md text-ink-700">{account.role_label}</span>
        </DetailRow>
        <DetailRow label={t("detail.status")}>
          <AccountStatusPill
            status={account.status}
            label={account.status_label}
          />
        </DetailRow>
        {detail ? (
          <>
            <DetailRow label={t("detail.firstLogin")}>
              <Time value={detail.first_login_at} mono />
            </DetailRow>
            <DetailRow label={t("detail.lastLogin")}>
              <Time value={detail.last_login_at} mono />
            </DetailRow>
            <DetailRow label={t("detail.lastLoginIp")}>
              <Mono>{detail.last_login_ip || "—"}</Mono>
            </DetailRow>
            <DetailRow label={t("detail.gatewayCount")}>
              <Mono>{detail.gateway_count}</Mono>
            </DetailRow>
            <DetailRow label={t("detail.appCount")}>
              <Mono>{detail.app_count}</Mono>
            </DetailRow>
          </>
        ) : (
          <div className="flex flex-col gap-2 px-1 py-1.5">
            <Skeleton className="h-5 w-full" />
            <Skeleton className="h-5 w-2/3" />
          </div>
        )}
        <DetailRow label={t("detail.created")}>
          <Time value={account.created_at} mono />
        </DetailRow>
        <DetailRow label={t("detail.modified")}>
          <Time value={account.modified_at} mono />
        </DetailRow>
      </DetailSection>

      {/* Login user agent as its own region below the fields. */}
      {detail?.last_login_user_agent ? (
        <DetailSection title={t("detail.userAgent")}>
          <div className="px-1 py-1.5">
            <span className="font-mono text-2xs break-all text-ink-500">
              {detail.last_login_user_agent}
            </span>
          </div>
        </DetailSection>
      ) : null}
    </div>
  );
}

/**
 * Drawer wrapper for the account detail. Mounted once at the list level and
 * driven by the selected account; retains the last account so the body stays
 * painted through the close animation.
 */
export function AccountDetailDrawer({
  account,
  open,
  onOpenChange,
}: {
  account: AccountBase | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("dashboard.admin.accounts");
  const shownRef = useRef<AccountBase | null>(account);
  if (account) {
    shownRef.current = account;
  }
  const active = account ?? shownRef.current;

  return (
    <DetailDrawer
      open={open}
      onOpenChange={onOpenChange}
      title={t("detail.title")}
      closeLabel={t("actions.hideDetails")}
    >
      {active ? <AccountDetailBody account={active} /> : null}
    </DetailDrawer>
  );
}
