"use client";

import { useTranslations } from "next-intl";
import { useId } from "react";

import type {
  RpcProviderNetworkPair,
  RpcProviderVendor,
} from "@/api/providers/client";
import { Field } from "@/components/patterns/form-field";
import { cn } from "@/lib/utils";

import { ChainNetworkMultiSelect } from "./chain-network-multi-select";

export type NetworkFilterMode = "none" | "only" | "ignore";

export function NetworkFilterField({
  vendor,
  mode,
  onModeChange,
  networks,
  onNetworksChange,
  busy,
  idPrefix,
}: {
  vendor: RpcProviderVendor;
  mode: NetworkFilterMode;
  onModeChange: (mode: NetworkFilterMode) => void;
  networks: RpcProviderNetworkPair[];
  onNetworksChange: (networks: RpcProviderNetworkPair[]) => void;
  busy: boolean;
  idPrefix: string;
}) {
  const t = useTranslations("dashboard.providers");
  const modeName = useId();
  const pairId = `${idPrefix}-chain-network`;

  const modeOptions: NetworkFilterMode[] = ["none", "only", "ignore"];
  const modeLabels: Record<NetworkFilterMode, string> = {
    none: t("form.networkFilterNone"),
    only: t("form.networkFilterOnly"),
    ignore: t("form.networkFilterIgnore"),
  };

  return (
    <>
      <Field label={t("form.networkFilter")} hint={t("form.networkFilterHint")}>
        <div
          role="radiogroup"
          aria-label={t("form.networkFilter")}
          className="grid grid-cols-3 gap-2"
        >
          {modeOptions.map((item) => {
            const active = item === mode;
            return (
              <label key={item} className="min-w-0">
                <input
                  id={`${idPrefix}-network-mode-${item}`}
                  type="radio"
                  name={modeName}
                  value={item}
                  checked={active}
                  disabled={busy}
                  onChange={() => onModeChange(item)}
                  className="peer sr-only"
                />
                <span
                  className={cn(
                    "flex min-h-10 cursor-pointer items-center justify-center rounded-xl bg-ink-wash px-2 py-2 text-center text-sm font-medium transition-colors",
                    "peer-focus-visible:ring-2 peer-focus-visible:ring-brand/30",
                    active
                      ? "bg-brand-soft text-brand"
                      : "text-ink-600 hover:bg-stripe",
                    busy && "cursor-not-allowed opacity-60",
                  )}
                >
                  {modeLabels[item]}
                </span>
              </label>
            );
          })}
        </div>
      </Field>

      {mode !== "none" ? (
        <Field label={t("form.chainNetwork")} htmlFor={pairId}>
          <ChainNetworkMultiSelect
            vendor={vendor}
            value={networks}
            onChange={onNetworksChange}
            disabled={busy}
            inputId={pairId}
          />
        </Field>
      ) : null}
    </>
  );
}
