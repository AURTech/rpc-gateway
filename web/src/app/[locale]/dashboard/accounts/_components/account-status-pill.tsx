import type { AccountStatus } from "@/api/accounts/client";
import { Badge } from "@/components/ui/badge";

const STATUS_VARIANT: Record<
  AccountStatus,
  React.ComponentProps<typeof Badge>["variant"]
> = {
  active: "positive",
  unactivated: "warning",
  disabled: "danger",
  archived: "neutral",
};

export function AccountStatusPill({
  status,
  label,
  className,
}: {
  status: AccountStatus;
  label: string;
  className?: string;
}) {
  return (
    <Badge variant={STATUS_VARIANT[status]} dot className={className}>
      {label}
    </Badge>
  );
}
