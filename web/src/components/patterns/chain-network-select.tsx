"use client";

import { useTranslations } from "next-intl";
import { useCallback, useMemo, useState } from "react";

import { ChainGroup as ChainIconGroup } from "@/components/ui/chain-group";
import { ChainIcon } from "@/components/ui/chain-icon";
import {
  Combobox,
  ComboboxChip,
  ComboboxChips,
  ComboboxChipsInput,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  ComboboxTrigger,
  ComboboxValue,
  useComboboxAnchor,
} from "@/components/ui/combobox";
import {
  CHAIN_CATALOG,
  CHAINS,
  type Chain,
  type Network,
} from "@/lib/blockchain";
import { chainLabel, networkLabel } from "@/lib/rpc-chain";

export interface ChainNetworkPair {
  chain: Chain;
  network: Network;
}

export const ALL_CHAIN_NETWORK_PAIRS: readonly ChainNetworkPair[] =
  CHAINS.flatMap((chain) =>
    CHAIN_CATALOG[chain].networks.map((network) => ({ chain, network })),
  );

export function chainNetworkValue(pair: ChainNetworkPair): string {
  return `${pair.chain}:${pair.network}`;
}

export function chainNetworkLabel(pair: ChainNetworkPair): string {
  return `${chainLabel(pair.chain)} · ${networkLabel(pair.chain, pair.network)}`;
}

export function ChainNetworkOptionContent({
  pair,
}: {
  pair: ChainNetworkPair;
}) {
  return (
    <>
      <ChainIcon
        chain={pair.chain}
        network={pair.network}
        className="size-4 shrink-0"
      />
      <span className="min-w-0 flex-1 truncate">{chainNetworkLabel(pair)}</span>
    </>
  );
}

function useChainNetworkOptions(options: readonly ChainNetworkPair[]) {
  const values = useMemo(() => options.map(chainNetworkValue), [options]);
  const byValue = useMemo(
    () => new Map(options.map((pair) => [chainNetworkValue(pair), pair])),
    [options],
  );
  const itemToLabel = useCallback(
    (item: string) => {
      const pair = byValue.get(item);
      return pair ? chainNetworkLabel(pair) : item;
    },
    [byValue],
  );
  const filter = useCallback(
    (item: string, query: string) =>
      itemToLabel(item).toLocaleLowerCase().includes(query.toLocaleLowerCase()),
    [itemToLabel],
  );

  return { values, byValue, itemToLabel, filter };
}

function FlatChainNetworkOptions({
  byValue,
}: {
  byValue: ReadonlyMap<string, ChainNetworkPair>;
}) {
  const t = useTranslations("dashboard.networkSelect");

  return (
    <>
      <ComboboxEmpty>{t("empty")}</ComboboxEmpty>
      <ComboboxList>
        {(item: string) => {
          const pair = byValue.get(item);
          return pair ? (
            <ComboboxItem key={item} value={item}>
              <ChainNetworkOptionContent pair={pair} />
            </ComboboxItem>
          ) : null;
        }}
      </ComboboxList>
    </>
  );
}

function useOverlayContainer() {
  const [container, setContainer] = useState<HTMLElement | null>(null);
  const captureContainer = useCallback((node: HTMLElement | null) => {
    setContainer(
      node?.closest<HTMLElement>(
        '[data-slot="sheet-content"], [data-slot="dialog-content"]',
      ) ?? null,
    );
  }, []);

  return { container, captureContainer };
}

export function ChainNetworkSelect({
  disabled = false,
  inputId,
  onChange,
  options = ALL_CHAIN_NETWORK_PAIRS,
  value,
}: {
  disabled?: boolean;
  inputId: string;
  onChange: (next: ChainNetworkPair) => void;
  options?: readonly ChainNetworkPair[];
  value: ChainNetworkPair;
}) {
  const t = useTranslations("dashboard.networkSelect");
  const { values, byValue, itemToLabel, filter } =
    useChainNetworkOptions(options);
  const { container, captureContainer } = useOverlayContainer();
  const selectedValue = chainNetworkValue(value);
  const selectedPair = byValue.get(selectedValue);

  return (
    <Combobox
      items={values}
      autoHighlight
      value={selectedValue}
      onValueChange={(next) => {
        const pair = typeof next === "string" ? byValue.get(next) : undefined;
        if (pair) onChange(pair);
      }}
      itemToStringLabel={itemToLabel}
      filter={filter}
      disabled={disabled}
    >
      <div ref={captureContainer} className="relative">
        {selectedPair ? (
          <ChainIcon
            chain={selectedPair.chain}
            network={selectedPair.network}
            className="pointer-events-none absolute top-1/2 left-3 z-10 size-4 -translate-y-1/2"
          />
        ) : null}
        <ComboboxInput
          id={inputId}
          className="w-full [&_input]:pl-9"
          placeholder={t("placeholder")}
          autoComplete="off"
          spellCheck={false}
          disabled={disabled}
        />
      </div>
      <ComboboxContent container={container ?? undefined}>
        <FlatChainNetworkOptions byValue={byValue} />
      </ComboboxContent>
    </Combobox>
  );
}

export function ChainNetworkMultiSelect({
  value,
  onChange,
  options,
  disabled = false,
  inputId,
}: {
  value: ChainNetworkPair[];
  onChange: (next: ChainNetworkPair[]) => void;
  options: readonly ChainNetworkPair[];
  disabled?: boolean;
  inputId: string;
}) {
  const t = useTranslations("dashboard.networkSelect");
  const anchorRef = useComboboxAnchor();
  const { container, captureContainer } = useOverlayContainer();
  const { values, byValue, itemToLabel, filter } =
    useChainNetworkOptions(options);
  const selected = useMemo(() => value.map(chainNetworkValue), [value]);

  const setAnchor = useCallback(
    (node: HTMLDivElement | null) => {
      anchorRef.current = node;
      captureContainer(node);
    },
    [anchorRef, captureContainer],
  );

  const applySelection = (next: string[]) => {
    const picked = new Set(next);
    onChange(options.filter((pair) => picked.has(chainNetworkValue(pair))));
  };

  return (
    <div className="flex flex-col gap-2">
      <Combobox
        items={values}
        multiple
        autoHighlight
        disabled={disabled}
        value={selected}
        onValueChange={(next) => applySelection(next as string[])}
        itemToStringLabel={itemToLabel}
        filter={filter}
      >
        <ComboboxChips ref={setAnchor} className="relative rounded-xl pr-9">
          <ComboboxValue>
            {(items: string[]) =>
              items.length === 0 ? (
                <div role="img" aria-label={t("allNetworks")} className="px-1">
                  <ChainIconGroup chains={options.map((pair) => pair.chain)} />
                </div>
              ) : (
                items.map((item) => {
                  const pair = byValue.get(item);
                  return (
                    <ComboboxChip key={item}>
                      {pair ? (
                        <ChainIcon
                          chain={pair.chain}
                          network={pair.network}
                          className="size-3.5 shrink-0"
                        />
                      ) : null}
                      {itemToLabel(item)}
                    </ComboboxChip>
                  );
                })
              )
            }
          </ComboboxValue>
          <ComboboxChipsInput
            id={inputId}
            placeholder={t("placeholder")}
            autoComplete="off"
            spellCheck={false}
          />
          <ComboboxTrigger
            aria-label={t("openMenu")}
            className="absolute inset-y-0 right-0 flex w-9 items-center justify-center rounded-r-md text-ink-400 transition-colors hover:text-ink-700 disabled:cursor-not-allowed disabled:opacity-40"
          />
        </ComboboxChips>

        <ComboboxContent anchor={anchorRef} container={container ?? undefined}>
          <FlatChainNetworkOptions byValue={byValue} />
        </ComboboxContent>
      </Combobox>

      <p className="text-sm text-ink-500">
        {value.length > 0
          ? t("selected", { count: value.length })
          : t("allNetworksHint")}
      </p>
    </div>
  );
}
