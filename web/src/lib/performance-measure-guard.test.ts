import { describe, expect, it } from "vitest";

import {
  installPerformanceMeasureGuard,
  isNegativePerformanceMeasureError,
} from "./performance-measure-guard";

function performanceStub(measure: Performance["measure"]): Performance {
  return { measure } as Performance;
}

describe("isNegativePerformanceMeasureError", () => {
  it("matches Firefox-style negative performance.measure errors", () => {
    expect(
      isNegativePerformanceMeasureError(
        new TypeError(
          "Performance.measure: Given attribute end cannot be negative",
        ),
      ),
    ).toBe(true);
    expect(
      isNegativePerformanceMeasureError(
        new TypeError(
          "Failed to execute 'measure' on 'Performance': 'NotFound' cannot have a negative time stamp.",
        ),
      ),
    ).toBe(true);
  });

  it("does not match unrelated errors", () => {
    expect(isNegativePerformanceMeasureError(new Error("boom"))).toBe(false);
    expect(isNegativePerformanceMeasureError("Performance.measure")).toBe(
      false,
    );
  });
});

describe("installPerformanceMeasureGuard", () => {
  it("swallows only negative performance.measure errors", () => {
    const performance = performanceStub(() => {
      throw new TypeError(
        "Performance.measure: Given attribute end cannot be negative",
      );
    });

    installPerformanceMeasureGuard(performance);

    expect(() =>
      performance.measure("component", { start: 1, end: -1 }),
    ).not.toThrow();
  });

  it("rethrows unrelated measure errors", () => {
    const performance = performanceStub(() => {
      throw new TypeError("Performance.measure: The mark does not exist");
    });

    installPerformanceMeasureGuard(performance);

    expect(() => performance.measure("component", "missing")).toThrow(
      "The mark does not exist",
    );
  });

  it("installs once per performance object", () => {
    const originalMeasure = (() =>
      ({ duration: 1 }) as PerformanceMeasure) as Performance["measure"];
    const performance = performanceStub(originalMeasure);

    installPerformanceMeasureGuard(performance);
    const guardedMeasure = performance.measure;
    installPerformanceMeasureGuard(performance);

    expect(performance.measure).toBe(guardedMeasure);
  });
});
