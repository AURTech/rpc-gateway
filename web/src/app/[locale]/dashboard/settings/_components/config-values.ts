/**
 * Draft-string parsing shared by the settings config forms. Inputs keep their
 * value as the raw string the admin typed; these helpers narrow it to a valid
 * number (or null) at save/validation time.
 */

export function parseIntInRange(
  value: string,
  min: number,
  max: number,
): number | null {
  if (value.trim().length === 0) return null;
  const parsed = Number(value);
  if (!Number.isInteger(parsed)) return null;
  if (parsed < min || parsed > max) return null;
  return parsed;
}

export function parseFloatInRange(
  value: string,
  min: number,
  max: number,
): number | null {
  if (value.trim().length === 0) return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  if (parsed < min || parsed > max) return null;
  return parsed;
}
