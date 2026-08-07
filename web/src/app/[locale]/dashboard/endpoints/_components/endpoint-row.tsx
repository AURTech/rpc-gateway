"use client";

import { useTranslations } from "next-intl";

import type { Endpoint } from "@/api/endpoints/client";
import { Badge } from "@/components/ui/badge";
import { ChainIcon } from "@/components/ui/chain-icon";
import { Checkbox } from "@/components/ui/checkbox";
import { TableCell, TableRow } from "@/components/ui/table";

import { EndpointActionsMenu } from "./endpoint-actions-menu";
import { EndpointSourceTags } from "./endpoint-source-tags";
import type { EndpointColumnKey } from "./endpoints-content";

/**
 * One endpoint as a desktop table row — counterpart to the mobile
 * {@link EndpointCard}. Cells are gated by `visibleColumns` (driven by the
 * header's ColumnsToggle); the trailing cell holds the management menu.
 */
export function EndpointRow({
  endpoint,
  visibleColumns,
  selectable,
  bulkSelected,
  selected,
  togglePending,
  onSelect,
  onEdit,
  onAudit,
  onToggleEnabled,
  onDelete,
  onBulkSelect,
}: {
  endpoint: Endpoint;
  visibleColumns: Set<EndpointColumnKey>;
  selectable: boolean;
  bulkSelected: boolean;
  selected: boolean;
  togglePending: boolean;
  onSelect: (id: string) => void;
  onEdit: (endpoint: Endpoint) => void;
  onAudit: (endpoint: Endpoint) => void;
  onToggleEnabled: (endpoint: Endpoint) => void;
  onDelete: (endpoint: Endpoint) => void;
  onBulkSelect: (endpoint: Endpoint) => void;
}) {
  const t = useTranslations("dashboard.endpoints");

  return (
    <TableRow active={selected}>
      {selectable ? (
        <TableCell divider className="w-12">
          <Checkbox
            checked={bulkSelected}
            onCheckedChange={() => onBulkSelect(endpoint)}
            aria-label={t("bulk.selectEndpoint", { name: endpoint.name })}
          />
        </TableCell>
      ) : null}
      {visibleColumns.has("name") ? (
        <TableCell divider>
          <span className="truncate font-semibold text-ink-900">
            {endpoint.name}
          </span>
        </TableCell>
      ) : null}
      {visibleColumns.has("chain") ? (
        <TableCell divider>
          <span className="inline-flex items-center gap-2">
            <ChainIcon
              chain={endpoint.chain}
              network={endpoint.network}
              className="size-5"
            />
            <span className="font-medium text-ink-900">
              {t(`chain.${endpoint.chain}`)}
            </span>
          </span>
        </TableCell>
      ) : null}
      {visibleColumns.has("network") ? (
        <TableCell divider>
          <span className="font-medium text-ink-700">
            {t(`network.${endpoint.network}`)}
          </span>
        </TableCell>
      ) : null}
      {visibleColumns.has("protocol") ? (
        <TableCell divider>
          <span className="text-ink-700">
            {t(`protocol.${endpoint.protocol}`)}
          </span>
        </TableCell>
      ) : null}
      {visibleColumns.has("origin") ? (
        <TableCell divider>
          <EndpointSourceTags endpoint={endpoint} />
        </TableCell>
      ) : null}
      {visibleColumns.has("state") ? (
        <TableCell divider>
          <Badge dot variant={endpoint.enabled ? "positive" : "neutral"}>
            {endpoint.enabled ? t("state.enabled") : t("state.disabled")}
          </Badge>
        </TableCell>
      ) : null}
      <TableCell divider align="right">
        <EndpointActionsMenu
          endpoint={endpoint}
          selected={selected}
          togglePending={togglePending}
          onSelect={onSelect}
          onEdit={onEdit}
          onAudit={onAudit}
          onToggleEnabled={onToggleEnabled}
          onDelete={onDelete}
        />
      </TableCell>
    </TableRow>
  );
}
