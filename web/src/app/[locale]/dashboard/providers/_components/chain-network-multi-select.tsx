"use client";

import { useTranslations } from "next-intl";
import { useCallback, useMemo, useState } from "react";
import { providerSupportsNetwork } from "@/api/providers/capabilities";
import type {
  RpcProviderNetworkPair,
  RpcProviderVendor,
} from "@/api/providers/client";
import { ChainIcon } from "@/components/ui/chain-icon";
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
import {
  chainLabel,
  networkLabel,
  networksFor,
  RPC_CHAINS,
  type RpcChain,
  type RpcNetwork,
} from "@/lib/rpc-chain";

type ChainNetworkOption = {
  value: string;
  chain: RpcChain;
  network: RpcNetwork;
};

type ChainNetworkGroup = {
  value: string;
  items: string[];
};

const OPTIONS: ChainNetworkOption[] = RPC_CHAINS.flatMap((chain) =>
  networksFor(chain).map((network) => ({
    value: `${chain}:${network}`,
    chain,
    network,
  })),
);

const OPTION_BY_VALUE = new Map(
  OPTIONS.map((option) => [option.value, option]),
);

function pairValue(pair: RpcProviderNetworkPair) {
  return `${pair.chain}:${pair.network}`;
}

function optionLabel(value: string) {
  const option = OPTION_BY_VALUE.get(value);
  return option
    ? `${chainLabel(option.chain)} · ${networkLabel(option.chain, option.network)}`
    : value;
}

export function ChainNetworkMultiSelect({
  vendor,
  value,
  onChange,
  disabled = false,
  inputId,
}: {
  vendor: RpcProviderVendor;
  value: RpcProviderNetworkPair[];
  onChange: (next: RpcProviderNetworkPair[]) => void;
  disabled?: boolean;
  inputId: string;
}) {
  const t = useTranslations("dashboard.providers");
  const anchorRef = useComboboxAnchor();
  const [portalContainer, setPortalContainer] = useState<HTMLElement | null>(
    null,
  );
  const groups = useMemo<ChainNetworkGroup[]>(() => {
    const supportedOptions = OPTIONS.filter((option) =>
      providerSupportsNetwork(vendor, option),
    );
    const chains = RPC_CHAINS.filter((chain) =>
      supportedOptions.some((option) => option.chain === chain),
    );
    return chains.map((chain) => ({
      value: chain,
      items: supportedOptions
        .filter((option) => option.chain === chain)
        .map((option) => option.value),
    }));
  }, [vendor]);
  const selected = useMemo(() => value.map(pairValue), [value]);
  const itemToLabel = useCallback(optionLabel, []);
  const filterOption = useCallback(
    (item: string, query: string) =>
      optionLabel(item).toLocaleLowerCase().includes(query.toLocaleLowerCase()),
    [],
  );
  const setAnchor = useCallback(
    (node: HTMLDivElement | null) => {
      anchorRef.current = node;
      setPortalContainer(
        node?.closest<HTMLElement>(
          '[data-slot="sheet-content"], [data-slot="dialog-content"]',
        ) ?? null,
      );
    },
    [anchorRef],
  );

  return (
    <Combobox
      items={groups}
      multiple
      autoHighlight
      disabled={disabled}
      value={selected}
      onValueChange={(next) => {
        onChange(
          (next as string[]).flatMap((item) => {
            const option = OPTION_BY_VALUE.get(item);
            return option
              ? [{ chain: option.chain, network: option.network }]
              : [];
          }),
        );
      }}
      itemToStringLabel={itemToLabel}
      filter={filterOption}
    >
      <ComboboxChips ref={setAnchor} className="relative rounded-xl pr-9">
        <ComboboxValue>
          {(items: string[]) =>
            items.map((item) => {
              const option = OPTION_BY_VALUE.get(item);
              return (
                <ComboboxChip key={item}>
                  {option ? (
                    <ChainIcon
                      chain={option.chain}
                      network={option.network}
                      className="size-3.5 shrink-0"
                    />
                  ) : null}
                  {optionLabel(item)}
                </ComboboxChip>
              );
            })
          }
        </ComboboxValue>
        <ComboboxChipsInput
          id={inputId}
          placeholder={t("form.chainNetworkSearch")}
          autoComplete="off"
          spellCheck={false}
        />
        <ComboboxTrigger
          aria-label={t("form.openChainNetworks")}
          className="absolute inset-y-0 right-0 flex w-9 items-center justify-center rounded-r-md text-ink-400 transition-colors hover:text-ink-700 disabled:cursor-not-allowed disabled:opacity-40"
        />
      </ComboboxChips>

      <ComboboxContent
        anchor={anchorRef}
        container={portalContainer ?? undefined}
      >
        <ComboboxEmpty>{t("form.chainNetworkEmpty")}</ComboboxEmpty>
        <ComboboxList>
          {(group: ChainNetworkGroup) => (
            <ComboboxGroup key={group.value} items={group.items}>
              <ComboboxLabel>
                {chainLabel(group.value as RpcChain)}
              </ComboboxLabel>
              <ComboboxCollection>
                {(item: string) => {
                  const option = OPTION_BY_VALUE.get(item);
                  return option ? (
                    <ComboboxItem key={item} value={item}>
                      <ChainIcon
                        chain={option.chain}
                        network={option.network}
                        className="size-4 shrink-0"
                      />
                      <span className="min-w-0 flex-1 truncate">
                        {networkLabel(option.chain, option.network)}
                      </span>
                    </ComboboxItem>
                  ) : null;
                }}
              </ComboboxCollection>
            </ComboboxGroup>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
}
