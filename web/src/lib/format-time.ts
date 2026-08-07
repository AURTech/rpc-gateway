/**
 * Single source of truth for absolute timestamp formatting.
 *
 * The app fixes its display timezone to UTC (see `next-intl` `timeZone: "UTC"`
 * in `src/i18n/request.ts`), so every formatter here renders UTC — language
 * neutral, audit-friendly, and stable across server/client (no `Intl` locale,
 * no `Date.now()`), which keeps hydration deterministic.
 *
 * Pair these with the `<Time>` component (`components/ui/time.tsx`) so values
 * also carry a machine-readable `<time datetime>` and a full-precision hover
 * title. Use the raw functions only where a plain string is required.
 */

/**
 * ISO timestamp → `YYYY-MM-DD HH:mm` (UTC) — the table/list/detail display
 * format. Null/empty → an em dash; an unparseable value is returned verbatim.
 */
export function formatAbsolute(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  // ISO is `YYYY-MM-DDTHH:mm:ss.sssZ`; slice to minutes, then T → space.
  return d.toISOString().slice(0, 16).replace("T", " ");
}

/**
 * ISO timestamp → `YYYY-MM-DD HH:mm:ss UTC` — full precision for the hover
 * title, surfacing the seconds and timezone that {@link formatAbsolute} drops.
 * Returns null for missing/unparseable input so callers can omit the title.
 */
export function formatAbsoluteFull(
  value: string | null | undefined,
): string | null {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return `${d.toISOString().slice(0, 19).replace("T", " ")} UTC`;
}
