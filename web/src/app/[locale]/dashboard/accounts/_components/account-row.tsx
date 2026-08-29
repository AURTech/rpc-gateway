"use client";

import type { AccountBase } from "@/api/accounts/client";
import { TableCell, TableRow } from "@/components/ui/table";
import { Time } from "@/components/ui/time";

import { AccountRowActions } from "./account-row-actions";
import { AccountStatusPill } from "./account-status-pill";
import type { AccountColumnKey } from "./accounts-content";

export function AccountRow({
  account,
  visibleColumns,
  selected,
  onSelect,
  enterIndex,
}: {
  account: AccountBase;
  visibleColumns: Set<AccountColumnKey>;
  selected: boolean;
  onSelect: (id: string) => void;
  enterIndex?: number;
}) {
  return (
    <TableRow active={selected} enterIndex={enterIndex}>
      {visibleColumns.has("email") ? (
        <TableCell divider>
          <div className="flex min-w-0 flex-col">
            <span className="truncate text-md font-semibold text-ink-900">
              {account.email}
            </span>
            {account.name ? (
              <span className="truncate text-sm text-ink-400">
                {account.name}
              </span>
            ) : null}
          </div>
        </TableCell>
      ) : null}
      {visibleColumns.has("role") ? (
        <TableCell divider className="text-ink-500">
          {account.role_label}
        </TableCell>
      ) : null}
      {visibleColumns.has("status") ? (
        <TableCell divider>
          <AccountStatusPill account={account} />
        </TableCell>
      ) : null}
      {visibleColumns.has("created") ? (
        <TableCell divider className="text-ink-500">
          <Time value={account.created_at} />
        </TableCell>
      ) : null}
      <TableCell divider align="right">
        <AccountRowActions
          account={account}
          selected={selected}
          onSelect={onSelect}
        />
      </TableCell>
    </TableRow>
  );
}
