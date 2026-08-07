const GUARD_FLAG = "__rpcGatewayPerformanceMeasureGuard";

type GuardedPerformance = Performance & {
  [GUARD_FLAG]?: true;
};

type PerformanceMeasureFn = (
  measureName: string,
  startOrMeasureOptions?: string | PerformanceMeasureOptions,
  endMark?: string,
) => PerformanceMeasure;

export function isNegativePerformanceMeasureError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;

  const message = error.message.toLowerCase();
  const isPerformanceMeasureError =
    message.includes("performance.measure") ||
    (message.includes("performance") && message.includes("measure"));

  return (
    isPerformanceMeasureError &&
    (message.includes("end cannot be negative") ||
      message.includes("negative time stamp") ||
      message.includes("negative timestamp"))
  );
}

export function installPerformanceMeasureGuard(
  performanceTarget: Performance | undefined = globalThis.performance,
): void {
  if (!performanceTarget || typeof performanceTarget.measure !== "function") {
    return;
  }

  const guarded = performanceTarget as GuardedPerformance;
  if (guarded[GUARD_FLAG]) return;

  const originalMeasure = performanceTarget.measure.bind(
    performanceTarget,
  ) as PerformanceMeasureFn;

  guarded.measure = ((measureName, startOrMeasureOptions, endMark) => {
    try {
      return originalMeasure(measureName, startOrMeasureOptions, endMark);
    } catch (error) {
      if (isNegativePerformanceMeasureError(error)) {
        return undefined as unknown as PerformanceMeasure;
      }
      throw error;
    }
  }) as Performance["measure"];
  guarded[GUARD_FLAG] = true;
}
