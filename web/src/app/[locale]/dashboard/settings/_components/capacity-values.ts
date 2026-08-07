import { parseFloatInRange } from "./config-values";

export const MIB_BYTES = 1024 * 1024;
export const GIB_BYTES = 1024 * MIB_BYTES;
export const KIB_BYTES = 1024;

export function formatCapacityBytes(bytes: number, unitBytes: number): string {
  const value = bytes / unitBytes;
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

export function parseCapacityBytes(
  value: string,
  unitBytes: number,
  maxBytes: number,
): number | null {
  const maxUnits = maxBytes / unitBytes;
  const parsed = parseFloatInRange(value, 1 / unitBytes, maxUnits);
  if (parsed === null) return null;
  const bytes = Math.round(parsed * unitBytes);
  if (!Number.isSafeInteger(bytes) || bytes < 1 || bytes > maxBytes) {
    return null;
  }
  return bytes;
}

export function formatCapacityUsage(bytes: number): string {
  if (bytes >= GIB_BYTES) {
    return `${formatCapacityBytes(bytes, GIB_BYTES)} GiB`;
  }
  if (bytes >= MIB_BYTES) {
    return `${formatCapacityBytes(bytes, MIB_BYTES)} MiB`;
  }
  if (bytes >= KIB_BYTES) {
    return `${formatCapacityBytes(bytes, KIB_BYTES)} KiB`;
  }
  return `${bytes.toLocaleString()} Bytes`;
}
