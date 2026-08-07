"use client";

import { useTranslations } from "next-intl";
import {
  type KeyboardEvent,
  useCallback,
  useMemo,
  useRef,
  useState,
} from "react";

import type { RpcMethodProtocol } from "@/api/rpc-methods/client";
import { Badge } from "@/components/ui/badge";
import {
  Combobox,
  ComboboxChip,
  ComboboxChips,
  ComboboxChipsInput,
  ComboboxCollection,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxGroup,
  ComboboxItem,
  ComboboxLabel,
  ComboboxList,
  ComboboxTrigger,
  ComboboxValue,
  useComboboxAnchor,
} from "@/components/ui/combobox";
import { useRpcMethodsQuery } from "@/hooks/use-rpc-methods";

const RISK_VARIANT = {
  read: "neutral",
  write: "warning",
  sensitive: "danger",
} as const;

type MethodGroup = { value: string; items: string[] };

/**
 * Multi-select for JSON-RPC methods, scoped to a chain protocol's catalog. Built
 * on the shadcn/base-ui Combobox using its data-driven (`items`) multiple-select
 * pattern: selected methods render as removable chips, the menu stays open while
 * picking several, and candidates are grouped by namespace. Methods already
 * owned by another rule (`assigned`) are dropped from the source list — the
 * server rejects duplicates across rules. Selection is held by the parent via
 * `value` (an array of method value strings). With a non-empty query, Tab
 * accepts the automatically highlighted match without moving focus.
 */
export function MethodMultiSelect({
  protocol,
  value,
  assigned,
  onChange,
  disabled,
}: {
  protocol: RpcMethodProtocol;
  value: string[];
  /** Methods already used by other rules on this gateway; never selectable. */
  assigned: ReadonlySet<string>;
  onChange: (next: string[]) => void;
  disabled?: boolean;
}) {
  const t = useTranslations("dashboard.gateways");
  const { data, isLoading, isError } = useRpcMethodsQuery({ protocol });
  const [query, setQuery] = useState("");
  const [highlightedMethod, setHighlightedMethod] = useState<
    string | undefined
  >();
  const itemRefs = useRef(new Map<string, HTMLElement>());
  // Anchor the menu to the whole chips field, not the inner text input — with
  // chips selected the input drifts right, which would otherwise offset the menu.
  const anchorRef = useComboboxAnchor();

  const methods = useMemo(
    () => data?.items.find((g) => g.protocol === protocol)?.methods ?? [],
    [data, protocol],
  );
  const byValue = useMemo(
    () => new Map(methods.map((m) => [m.value, m])),
    [methods],
  );

  // Grouped source data (method value strings per namespace), excluding methods
  // already claimed by other rules. Base UI filters this by the query for us.
  const groups = useMemo<MethodGroup[]>(() => {
    const map = new Map<string, string[]>();
    for (const m of methods) {
      if (assigned.has(m.value)) continue;
      const list = map.get(m.namespace_label) ?? [];
      list.push(m.value);
      map.set(m.namespace_label, list);
    }
    return [...map.entries()].map(([label, items]) => ({
      value: label,
      items,
    }));
  }, [methods, assigned]);

  // Base UI filters/labels items by this; our list values are method ids.
  const itemToLabel = useCallback(
    (item: string) => byValue.get(item)?.label ?? item,
    [byValue],
  );

  const completeHighlightedMethod = (
    event: KeyboardEvent<HTMLInputElement>,
  ) => {
    if (
      event.key !== "Tab" ||
      event.shiftKey ||
      event.ctrlKey ||
      event.altKey ||
      event.metaKey ||
      event.nativeEvent.isComposing ||
      query.trim().length === 0 ||
      !highlightedMethod
    ) {
      return;
    }

    const item = itemRefs.current.get(highlightedMethod);
    if (!item) return;

    event.preventDefault();
    // Reuse Base UI's item selection path so it also clears the query and
    // updates popup/highlight state exactly like a pointer or Enter selection.
    item.click();
  };

  return (
    <Combobox
      items={groups}
      multiple
      autoHighlight
      disabled={disabled}
      value={value}
      onValueChange={(next) => onChange(next as string[])}
      onInputValueChange={setQuery}
      onItemHighlighted={setHighlightedMethod}
      itemToStringLabel={itemToLabel}
    >
      <ComboboxChips ref={anchorRef} className="relative rounded-xl pr-9">
        <ComboboxValue>
          {(selected: string[]) =>
            selected.map((v) => (
              <ComboboxChip key={v}>{itemToLabel(v)}</ComboboxChip>
            ))
          }
        </ComboboxValue>
        <ComboboxChipsInput
          placeholder={t("methodRoutes.form.searchPlaceholder")}
          autoComplete="off"
          spellCheck={false}
          onKeyDown={completeHighlightedMethod}
        />
        {/* Explicit dropdown affordance: without it the chips field reads as a
            plain search box even though clicking it opens the catalog. */}
        <ComboboxTrigger
          aria-label={t("methodRoutes.form.openMethods")}
          className="absolute inset-y-0 right-0 flex w-9 items-center justify-center rounded-r-md text-ink-400 transition-colors hover:text-ink-700 disabled:cursor-not-allowed disabled:opacity-40"
        />
      </ComboboxChips>

      <ComboboxContent anchor={anchorRef}>
        {isLoading ? (
          <p className="px-3 py-3 text-sm text-ink-400">
            {t("methodRoutes.form.loadingMethods")}
          </p>
        ) : isError ? (
          <p className="px-3 py-3 text-sm text-danger">
            {t("methodRoutes.form.methodsError")}
          </p>
        ) : (
          <>
            <ComboboxEmpty>{t("methodRoutes.form.noMethods")}</ComboboxEmpty>
            <ComboboxList>
              {/* Render-prop form: Base UI feeds the query-FILTERED groups here.
                  Mapping the raw `groups` instead would bypass search entirely. */}
              {(group: MethodGroup) => (
                <ComboboxGroup key={group.value} items={group.items}>
                  <ComboboxLabel>{group.value}</ComboboxLabel>
                  <ComboboxCollection>
                    {(item: string) => {
                      const m = byValue.get(item);
                      return (
                        <ComboboxItem
                          key={item}
                          ref={(node) => {
                            if (node) itemRefs.current.set(item, node);
                            else itemRefs.current.delete(item);
                          }}
                          value={item}
                        >
                          <span className="min-w-0 flex-1 truncate font-mono text-sm font-medium text-ink-900">
                            {m?.label ?? item}
                            {m?.deprecated ? (
                              <span className="ml-1.5 font-sans text-2xs text-ink-400">
                                {t("methodRoutes.form.deprecated")}
                              </span>
                            ) : null}
                          </span>
                          {m ? (
                            <Badge variant={RISK_VARIANT[m.risk]}>
                              {m.risk_label}
                            </Badge>
                          ) : null}
                        </ComboboxItem>
                      );
                    }}
                  </ComboboxCollection>
                </ComboboxGroup>
              )}
            </ComboboxList>
          </>
        )}
      </ComboboxContent>
    </Combobox>
  );
}
