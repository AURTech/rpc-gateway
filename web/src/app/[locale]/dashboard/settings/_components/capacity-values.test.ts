import { describe, expect, it } from "vitest";

import {
  formatCapacityBytes,
  formatCapacityUsage,
  GIB_BYTES,
  MIB_BYTES,
  parseCapacityBytes,
} from "./capacity-values";

describe("capacity values", () => {
  it("converts MiB and GiB drafts to API bytes", () => {
    expect(parseCapacityBytes("8", MIB_BYTES, 16 * MIB_BYTES)).toBe(
      8 * MIB_BYTES,
    );
    expect(parseCapacityBytes("1.5", GIB_BYTES, 2 * GIB_BYTES)).toBe(
      1.5 * GIB_BYTES,
    );
  });

  it("rejects values beyond the byte ceiling", () => {
    expect(parseCapacityBytes("2.1", GIB_BYTES, 2 * GIB_BYTES)).toBeNull();
  });

  it("formats exact and fractional capacities", () => {
    expect(formatCapacityBytes(256 * MIB_BYTES, MIB_BYTES)).toBe("256");
    expect(formatCapacityUsage(1.5 * GIB_BYTES)).toBe("1.5 GiB");
    expect(formatCapacityUsage(1536)).toBe("1.5 KiB");
    expect(formatCapacityUsage(512)).toBe("512 Bytes");
  });
});
