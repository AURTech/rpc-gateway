import type { RpcProviderBase } from "@/api/providers/client";

/** Product/account metadata keys the card surfaces from `provider.settings`,
 *  in display order. Values are operator-supplied and often absent. */
export const PROVIDER_META_KEYS = [
  "type",
  "project",
  "organization",
  "region",
] as const;

export type ProviderMetaKey = (typeof PROVIDER_META_KEYS)[number];

export type ProviderMeta = {
  fields: { key: ProviderMetaKey; value: string }[];
  tags: string[];
};

function asNonEmptyString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0
    ? value.trim()
    : null;
}

/**
 * Reads the known product-metadata fields out of a provider's freeform
 * `settings` bag with runtime guards, dropping anything missing or malformed.
 * `settings` is typed as an opaque record on the client, so every read is
 * validated here rather than trusted.
 */
export function readProviderMeta(provider: RpcProviderBase): ProviderMeta {
  const settings = provider.settings ?? {};

  const fields: ProviderMeta["fields"] = [];
  for (const key of PROVIDER_META_KEYS) {
    const value = asNonEmptyString((settings as Record<string, unknown>)[key]);
    if (value) fields.push({ key, value });
  }

  const rawTags = (settings as Record<string, unknown>).tag_labels;
  const tags = Array.isArray(rawTags)
    ? rawTags.map(asNonEmptyString).filter((tag): tag is string => tag !== null)
    : [];

  return { fields, tags };
}
