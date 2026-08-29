import { useTranslations } from "next-intl";

import type { AccountBase, AccountStatus } from "@/api/accounts/client";
import { Badge } from "@/components/ui/badge";

const STATUS_VARIANT: Record<
  AccountStatus,
  React.ComponentProps<typeof Badge>["variant"]
> = {
  active: "positive",
  disabled: "danger",
  archived: "neutral",
};

/**
 * Status badge. An active account that has never signed in is still awaiting
 * its own first sign-in, so it reads as "Invited" instead of "Active".
 */
export function AccountStatusPill({
  account,
  className,
}: {
  account: AccountBase;
  className?: string;
}) {
  const t = useTranslations("dashboard.admin.accounts");
  const invited = !account.activated && account.status === "active";

  return (
    <Badge
      variant={invited ? "warning" : STATUS_VARIANT[account.status]}
      className={className}
    >
      {invited ? t("status.invited") : account.status_label}
    </Badge>
  );
}
