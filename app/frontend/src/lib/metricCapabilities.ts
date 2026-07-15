/**
 * Planning metric capability registry (audit F-11).
 *
 * Mirrors backend `metric_capabilities.PLANNING_CAPABILITIES` for wizard/preview
 * decisions so frontend unions do not drift independently of the design families.
 */

export const PLANNING_METRIC_TYPES = ["binary", "continuous", "ratio", "count"] as const;

export type PlanningMetricType = (typeof PLANNING_METRIC_TYPES)[number];

export type PlanningCapability = {
  metricType: PlanningMetricType;
  sampleSizePlanning: boolean;
  requiresStdDev: boolean;
  livePrimaryStats: boolean;
  cupedEligible: boolean;
  postHocRoute: "results" | "results_ratio" | "none";
};

export const PLANNING_CAPABILITIES: Record<PlanningMetricType, PlanningCapability> = {
  binary: {
    metricType: "binary",
    sampleSizePlanning: true,
    requiresStdDev: false,
    livePrimaryStats: true,
    cupedEligible: false,
    postHocRoute: "results"
  },
  continuous: {
    metricType: "continuous",
    sampleSizePlanning: true,
    requiresStdDev: true,
    livePrimaryStats: true,
    cupedEligible: true,
    postHocRoute: "results"
  },
  ratio: {
    metricType: "ratio",
    sampleSizePlanning: true,
    requiresStdDev: true,
    livePrimaryStats: true,
    cupedEligible: false,
    postHocRoute: "results_ratio"
  },
  count: {
    metricType: "count",
    sampleSizePlanning: true,
    requiresStdDev: false,
    livePrimaryStats: true,
    cupedEligible: false,
    postHocRoute: "results"
  }
};

export function isPlanningMetricType(value: string): value is PlanningMetricType {
  return (PLANNING_METRIC_TYPES as readonly string[]).includes(value);
}

export function requiresStdDevForPlanning(metricType: string): boolean {
  if (!isPlanningMetricType(metricType)) {
    return false;
  }
  return PLANNING_CAPABILITIES[metricType].requiresStdDev;
}

export function planningCapability(metricType: string): PlanningCapability | null {
  if (!isPlanningMetricType(metricType)) {
    return null;
  }
  return PLANNING_CAPABILITIES[metricType];
}
