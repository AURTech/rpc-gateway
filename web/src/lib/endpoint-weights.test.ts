import { describe, expect, it } from "vitest";

import {
  clampWeight,
  evenWeights,
  isValidWeight,
  sharePercents,
  weightsSum,
  weightsValid,
} from "./endpoint-weights";

describe("isValidWeight", () => {
  it("accepts integers in [1, 1000]", () => {
    expect(isValidWeight(1)).toBe(true);
    expect(isValidWeight(100)).toBe(true);
    expect(isValidWeight(1000)).toBe(true);
  });

  it("rejects out-of-range, non-integer, or missing values", () => {
    expect(isValidWeight(0)).toBe(false);
    expect(isValidWeight(1001)).toBe(false);
    expect(isValidWeight(1.5)).toBe(false);
    expect(isValidWeight(undefined)).toBe(false);
  });
});

describe("weightsValid", () => {
  it("requires a non-empty pool with every weight valid", () => {
    expect(weightsValid([], {})).toBe(false);
    expect(weightsValid(["a"], { a: 1 })).toBe(true);
    expect(weightsValid(["a", "b"], { a: 1 })).toBe(false);
    expect(weightsValid(["a", "b"], { a: 1, b: 0 })).toBe(false);
  });
});

describe("clampWeight", () => {
  it("clamps into range and rounds", () => {
    expect(clampWeight(0)).toBe(1);
    expect(clampWeight(5000)).toBe(1000);
    expect(clampWeight(2.6)).toBe(3);
  });

  it("defaults non-finite values to 100", () => {
    expect(clampWeight(undefined)).toBe(100);
    expect(clampWeight(Number.NaN)).toBe(100);
  });
});

describe("evenWeights", () => {
  it("assigns every id a weight of 1", () => {
    expect(evenWeights(["a", "b", "c"])).toEqual({ a: 1, b: 1, c: 1 });
  });
});

describe("weightsSum", () => {
  it("sums finite weights and ignores missing ones", () => {
    expect(weightsSum(["a", "b", "c"], { a: 2, b: 3 })).toBe(5);
  });
});

describe("sharePercents", () => {
  it("normalizes to integers that total 100", () => {
    const shares = sharePercents(["a", "b"], { a: 2, b: 1 });
    expect(shares).toEqual({ a: 67, b: 33 });
    expect(shares.a + shares.b).toBe(100);
  });

  it("splits an even pool evenly", () => {
    expect(sharePercents(["a", "b"], { a: 1, b: 1 })).toEqual({ a: 50, b: 50 });
  });

  it("distributes the remainder without drift", () => {
    const shares = sharePercents(["a", "b", "c"], { a: 1, b: 1, c: 1 });
    expect(shares.a + shares.b + shares.c).toBe(100);
  });

  it("returns {} for an empty or invalid pool", () => {
    expect(sharePercents([], {})).toEqual({});
    expect(sharePercents(["a"], { a: 0 })).toEqual({});
  });
});
