import { describe, expect, it } from "vitest";

import {
  PLANNING_CAPABILITIES,
  PLANNING_METRIC_TYPES,
  isPlanningMetricType,
  planningCapability,
  requiresStdDevForPlanning
} from "./metricCapabilities";

describe("metricCapabilities", () => {
  it("covers the four planning families", () => {
    expect(PLANNING_METRIC_TYPES).toEqual(["binary", "continuous", "ratio", "count"]);
    expect(Object.keys(PLANNING_CAPABILITIES).sort()).toEqual([...PLANNING_METRIC_TYPES].sort());
  });

  it("flags std_dev requirements for continuous and ratio only", () => {
    expect(requiresStdDevForPlanning("binary")).toBe(false);
    expect(requiresStdDevForPlanning("count")).toBe(false);
    expect(requiresStdDevForPlanning("continuous")).toBe(true);
    expect(requiresStdDevForPlanning("ratio")).toBe(true);
    expect(requiresStdDevForPlanning("fisher_exact")).toBe(false);
  });

  it("routes ratio post-hoc separately from the two-sample results family", () => {
    expect(planningCapability("ratio")?.postHocRoute).toBe("results_ratio");
    expect(planningCapability("count")?.postHocRoute).toBe("results");
    expect(isPlanningMetricType("count")).toBe(true);
    expect(isPlanningMetricType("mann_whitney")).toBe(false);
  });
});
