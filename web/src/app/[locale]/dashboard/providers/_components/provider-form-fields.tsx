"use client";

import { useTranslations } from "next-intl";
import {
  providerNetworksForVendor,
  providerSupportsNetwork,
} from "@/api/providers/capabilities";
import {
  RPC_PROVIDER_VENDORS,
  type RpcProviderNetworkPair,
  type RpcProviderVendor,
} from "@/api/providers/client";
import { ChainNetworkMultiSelect } from "@/components/patterns/chain-network-select";
import { Field } from "@/components/patterns/form-field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";

export const PROVIDER_NAME_MAX = 128;
export const PROVIDER_SECRET_MAX = 4096;

export type ProviderFormValues = {
  name: string;
  vendor: RpcProviderVendor;
  secret: string;
  syncEnabled: boolean;
  enabled: boolean;
  networks: RpcProviderNetworkPair[];
};

export const INITIAL_PROVIDER_FORM: ProviderFormValues = {
  name: "",
  vendor: "alchemy",
  secret: "",
  syncEnabled: false,
  enabled: true,
  networks: [],
};

type ProviderFormChange = <K extends keyof ProviderFormValues>(
  key: K,
  value: ProviderFormValues[K],
) => void;

/** New-provider fields mirror Provider settings, with vendor selection added. */
export function ProviderFormFields({
  values,
  onChange,
  busy,
  idPrefix,
}: {
  values: ProviderFormValues;
  onChange: ProviderFormChange;
  busy: boolean;
  idPrefix: string;
}) {
  const t = useTranslations("dashboard.providers");
  const nameId = `${idPrefix}-name`;
  const vendorId = `${idPrefix}-vendor`;
  const secretId = `${idPrefix}-secret`;
  const syncId = `${idPrefix}-sync`;
  const networksId = `${idPrefix}-networks`;
  const enabledId = `${idPrefix}-enabled`;
  const secretHelp =
    values.vendor === "drpc" ? t("form.drpcSecretHint") : t("form.secretHint");
  const secretPlaceholder =
    values.vendor === "drpc"
      ? t("form.drpcSecretPlaceholder")
      : t("form.secretPlaceholder");

  return (
    <>
      <div className="max-w-xl">
        <Field label={t("form.name")} htmlFor={nameId} required>
          <Input
            id={nameId}
            type="text"
            autoComplete="off"
            maxLength={PROVIDER_NAME_MAX}
            value={values.name}
            onChange={(event) => onChange("name", event.target.value)}
            disabled={busy}
          />
        </Field>
      </div>

      <div className="max-w-xl">
        <Field
          label={t("form.vendor")}
          htmlFor={vendorId}
          hint={t("form.vendorHint")}
          required
        >
          <Select
            value={values.vendor}
            onValueChange={(value) => {
              const vendor = value as RpcProviderVendor;
              onChange("vendor", vendor);
              onChange(
                "networks",
                values.networks.filter((pair) =>
                  providerSupportsNetwork(vendor, pair),
                ),
              );
            }}
            disabled={busy}
          >
            <SelectTrigger id={vendorId} aria-label={t("form.vendor")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {RPC_PROVIDER_VENDORS.map((vendor) => (
                <SelectItem key={vendor} value={vendor}>
                  {t(`vendor.${vendor}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      </div>

      <div className="max-w-xl">
        <Field
          label={t("form.secret")}
          htmlFor={secretId}
          hint={secretHelp}
          required
        >
          <Input
            id={secretId}
            type="password"
            autoComplete="new-password"
            spellCheck={false}
            maxLength={PROVIDER_SECRET_MAX}
            value={values.secret}
            onChange={(event) => onChange("secret", event.target.value)}
            placeholder={secretPlaceholder}
            disabled={busy}
          />
        </Field>
      </div>

      <div className="space-y-3">
        <p className="text-sm font-semibold text-ink-900">
          {t("form.networks")}
        </p>
        <ChainNetworkMultiSelect
          options={providerNetworksForVendor(values.vendor)}
          value={values.networks}
          onChange={(networks) => onChange("networks", networks)}
          disabled={busy}
          inputId={networksId}
        />
      </div>

      <div className="divide-y divide-table-frame">
        <div className="flex items-start justify-between gap-6 pb-4">
          <span>
            <span
              id={`${syncId}-label`}
              className="block text-sm font-semibold text-ink-900"
            >
              {t("form.autoSync")}
            </span>
            <span className="mt-1 block text-sm text-ink-500">
              {t("form.autoSyncHint")}
            </span>
          </span>
          <Switch
            id={syncId}
            aria-labelledby={`${syncId}-label`}
            checked={values.syncEnabled}
            onCheckedChange={(checked) => onChange("syncEnabled", checked)}
            disabled={busy}
          />
        </div>
        <div className="flex items-start justify-between gap-6 pt-4">
          <span>
            <span
              id={`${enabledId}-label`}
              className="block text-sm font-semibold text-ink-900"
            >
              {t("form.enabled")}
            </span>
            <span className="mt-1 block text-sm text-ink-500">
              {t("form.enabledHint")}
            </span>
          </span>
          <Switch
            id={enabledId}
            aria-labelledby={`${enabledId}-label`}
            checked={values.enabled}
            onCheckedChange={(checked) => onChange("enabled", checked)}
            disabled={busy}
          />
        </div>
      </div>
    </>
  );
}
