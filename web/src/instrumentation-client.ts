import { installPerformanceMeasureGuard } from "@/lib/performance-measure-guard";

if (process.env.NODE_ENV === "development") {
  installPerformanceMeasureGuard();
}
