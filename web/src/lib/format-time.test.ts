import { describe, expect, it } from "vitest";

import { formatAbsolute, formatAbsoluteFull } from "./format-time";

describe("formatAbsolute", () => {
  it("renders a UTC `YYYY-MM-DD HH:mm` to the minute", () => {
    expect(formatAbsolute("2026-06-29T14:32:05.000Z")).toBe("2026-06-29 14:32");
  });

  it("normalizes a zoned offset to UTC", () => {
    expect(formatAbsolute("2026-06-29T14:32:05+02:00")).toBe(
      "2026-06-29 12:32",
    );
  });

  it("falls back to an em dash for missing input", () => {
    expect(formatAbsolute(null)).toBe("—");
    expect(formatAbsolute(undefined)).toBe("—");
    expect(formatAbsolute("")).toBe("—");
  });

  it("returns an unparseable value verbatim", () => {
    expect(formatAbsolute("not a date")).toBe("not a date");
  });
});

describe("formatAbsoluteFull", () => {
  it("includes seconds and an explicit UTC marker", () => {
    expect(formatAbsoluteFull("2026-06-29T14:32:05.000Z")).toBe(
      "2026-06-29 14:32:05 UTC",
    );
  });

  it("returns null for missing or unparseable input", () => {
    expect(formatAbsoluteFull(null)).toBeNull();
    expect(formatAbsoluteFull("")).toBeNull();
    expect(formatAbsoluteFull("not a date")).toBeNull();
  });
});
