/**
 * Module factory for `vi.mock("next-intl", …)`. `useTranslations` echoes the
 * message key instead of resolving English copy, so assertions name the key and
 * survive rewording in `src/locales`:
 *
 * ```ts
 * vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());
 * ```
 *
 * Interpolated values are dropped by default. Pass `separator` when the
 * component builds an accessible name the test has to tell one row from
 * another by: `nextIntlMock({ separator: ":" })` renders
 * `t("bulk.selectEndpoint", { name })` as `bulk.selectEndpoint:endpoint-1`.
 */
export function nextIntlMock({ separator }: { separator?: string } = {}) {
  return {
    useLocale: () => "en",
    useTranslations:
      () =>
      (key: string, values?: Record<string, unknown>): string =>
        separator !== undefined && values
          ? `${key}${separator}${Object.values(values).join(separator)}`
          : key,
  };
}
