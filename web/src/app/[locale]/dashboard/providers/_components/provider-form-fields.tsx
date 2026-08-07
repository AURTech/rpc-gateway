"use client";

import { useTranslations } from "next-intl";
import { providerSupportsNetwork } from "@/api/providers/capabilities";
import {
  RPC_PROVIDER_VENDORS,
  type RpcProviderNetworkPair,
  type RpcProviderVendor,
} from "@/api/providers/client";
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
import {
  NetworkFilterField,
  type NetworkFilterMode,
} from "./network-filter-field";

export const PROVIDER_NAME_MAX = 128;
export const PROVIDER_SECRET_MAX = 4096;

export type ProviderFormValues = {
  name: string;
  vendor: RpcProviderVendor;
  secret: string;
  syncEnabled: boolean;
  enabled: boolean;
  netMode: NetworkFilterMode;
  networks: RpcProviderNetworkPair[];
};

export const INITIAL_PROVIDER_FORM: ProviderFormValues = {
  name: "",
  vendor: "alchemy",
  secret: "",
  syncEnabled: false,
  enabled: true,
  netMode: "none",
  networks: [],
};

type ProviderFormChange = <K extends keyof ProviderFormValues>(
  key: K,
  value: ProviderFormValues[K],
) => void;

function SwitchField({
  label,
  hint,
  checked,
  onCheckedChange,
  disabled,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled: boolean;
}) {
  return (
    <fieldset className="rounded-xl bg-ink-wash px-4 py-3.5">
      <legend className="sr-only">{label}</legend>
      <div className="flex items-center justify-between gap-4">
        <span className="text-md font-semibold text-ink-900">{label}</span>
        <Switch
          checked={checked}
          onCheckedChange={onCheckedChange}
          disabled={disabled}
          aria-label={label}
        />
      </div>
      <p className="mt-1 text-sm text-ink-500">{hint}</p>
    </fieldset>
  );
}

/** Shared provider fields keep create and edit order and layout identical. */
export function ProviderFormFields({
  values,
  onChange,
  busy,
  vendorLocked = false,
  secretHint,
  idPrefix,
  showEnabled = true,
}: {
  values: ProviderFormValues;
  onChange: ProviderFormChange;
  busy: boolean;
  vendorLocked?: boolean;
  secretHint?: string;
  idPrefix: string;
  showEnabled?: boolean;
}) {
  const t = useTranslations("dashboard.providers");
  const nameId = `${idPrefix}-name`;
  const vendorId = `${idPrefix}-vendor`;
  const secretId = `${idPrefix}-secret`;
  const secretHelp =
    values.vendor === "drpc"
      ? t(secretHint ? "form.drpcSecretKeepHint" : "form.drpcSecretHint")
      : (secretHint ?? t("form.secretHint"));
  const secretPlaceholder =
    values.vendor === "drpc"
      ? t("form.drpcSecretPlaceholder")
      : t("form.secretPlaceholder");

  return (
    <>
      <Field
        label={t("form.name")}
        htmlFor={nameId}
        hint={t("form.nameHint")}
        required
      >
        <Input
          id={nameId}
          type="text"
          autoComplete="off"
          maxLength={PROVIDER_NAME_MAX}
          value={values.name}
          onChange={(event) => onChange("name", event.target.value)}
          placeholder={t("form.namePlaceholder")}
          disabled={busy}
        />
      </Field>

      <Field
        label={t("form.vendor")}
        htmlFor={vendorId}
        hint={t(vendorLocked ? "form.vendorLocked" : "form.vendorHint")}
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
          disabled={busy || vendorLocked}
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

      <Field
        label={t("form.secret")}
        htmlFor={secretId}
        hint={secretHelp}
        required
      >
        <Input
          id={secretId}
          type="text"
          autoComplete="off"
          spellCheck={false}
          maxLength={PROVIDER_SECRET_MAX}
          value={values.secret}
          onChange={(event) => onChange("secret", event.target.value)}
          placeholder={secretPlaceholder}
          disabled={busy}
        />
      </Field>

      <SwitchField
        label={t("form.autoSync")}
        hint={t("form.autoSyncHint")}
        checked={values.syncEnabled}
        onCheckedChange={(checked) => onChange("syncEnabled", checked)}
        disabled={busy}
      />

      <NetworkFilterField
        vendor={values.vendor}
        mode={values.netMode}
        onModeChange={(mode) => {
          onChange("netMode", mode);
          if (mode === "none") onChange("networks", []);
        }}
        networks={values.networks}
        onNetworksChange={(networks) => onChange("networks", networks)}
        busy={busy}
        idPrefix={idPrefix}
      />

      {showEnabled ? (
        <SwitchField
          label={t("form.enabled")}
          hint={t("form.enabledHint")}
          checked={values.enabled}
          onCheckedChange={(checked) => onChange("enabled", checked)}
          disabled={busy}
        />
      ) : null}
    </>
  );
}
