import type { FullPayload, FullPayloadSectionKey, WizardStepKey } from "./types";
import { parseTrafficSplit } from "./payload";

function readString<T extends object, K extends keyof T>(section: T, key: K): string {
  return String(section[key] ?? "").trim();
}

function readNumber<T extends object, K extends keyof T>(section: T, key: K): number {
  const value = section[key];
  return typeof value === "number" ? value : Number(value);
}

const fieldIssueLookup: Record<string, string[]> = {
  "project.project_name": ["Project name is required."],
  "hypothesis.change_description": ["Change description is required."],
  "setup.traffic_split": [
    "Traffic split must contain at least two positive weights.",
    "Traffic split length must match variants count."
  ],
  "setup.expected_daily_traffic": ["Expected daily traffic must be greater than 0."],
  "setup.audience_share_in_test": ["Audience share in test must be between 0 and 1."],
  "setup.variants_count": ["Variants count must be an integer between 2 and 10."],
  "metrics.primary_metric_name": ["Primary metric name is required."],
  "metrics.baseline_value": [
    "Binary baseline value must be between 0 and 1.",
    "Continuous baseline value must be greater than 0."
  ],
  "metrics.mde_pct": ["MDE % must be greater than 0."],
  "metrics.alpha": ["Alpha must be between 0 and 1."],
  "metrics.power": ["Power must be between 0 and 1."],
  "metrics.std_dev": ["Continuous metrics require a positive std dev."],
  "metrics.cuped_pre_experiment_std": ["CUPED pre-experiment std dev must be positive."],
  "metrics.cuped_correlation": ["CUPED correlation must be between -1 and 1."],
  "constraints.desired_precision": ["Desired precision must be greater than 0 in Bayesian mode."],
  "constraints.credibility": ["Credibility must be between 0.5 and 1."],
  "metrics.guardrail_metrics": [
    "Guardrail metrics cannot exceed 3 items.",
    "Guardrail metric names are required.",
    "Binary guardrails require a baseline % between 0 and 100.",
    "Continuous guardrails require baseline mean and positive std dev.",
    "Guardrail metric type must be either binary or continuous."
  ]
};

const stepSections: WizardStepKey[] = [
  "project",
  "hypothesis",
  "setup",
  "metrics",
  "constraints",
  "review"
];

function resolveStepKey(step: number | WizardStepKey): WizardStepKey {
  if (typeof step === "number") {
    return stepSections[step] ?? "review";
  }

  return step;
}

function getStepPrefixes(step: WizardStepKey): string[] {
  if (step === "review") {
    return [];
  }

  return step === "constraints"
    ? ["constraints.", "additional_context.", "metrics.alpha", "metrics.power"]
    : [`${step}.`];
}

export function validateForm(state: FullPayload): string[] {
  const issues: string[] = [];
  const projectName = readString(state.project, "project_name");
  const changeDescription = readString(state.hypothesis, "change_description");
  const primaryMetricName = readString(state.metrics, "primary_metric_name");
  const metricType = readString(state.metrics, "metric_type");
  const trafficSplit = parseTrafficSplit(state.setup.traffic_split);
  const variantsCount = readNumber(state.setup, "variants_count");
  const expectedDailyTraffic = readNumber(state.setup, "expected_daily_traffic");
  const audienceShareInTest = readNumber(state.setup, "audience_share_in_test");
  const baselineValue = readNumber(state.metrics, "baseline_value");
  const mdePct = readNumber(state.metrics, "mde_pct");
  const alpha = readNumber(state.metrics, "alpha");
  const power = readNumber(state.metrics, "power");
  const analysisMode = state.constraints.analysis_mode ?? "frequentist";
  const desiredPrecisionRaw = state.constraints.desired_precision;
  const desiredPrecision =
    desiredPrecisionRaw === null || desiredPrecisionRaw === undefined
      ? null
      : Number(desiredPrecisionRaw);
  const credibility = readNumber(state.constraints, "credibility");
  const stdDevRaw = state.metrics.std_dev;
  const stdDev =
    stdDevRaw === "" || stdDevRaw === null || stdDevRaw === undefined ? null : Number(stdDevRaw);
  const cupedEnabled = state.metrics.cuped_enabled ?? false;
  const cupedPreExperimentStdRaw = state.metrics.cuped_pre_experiment_std;
  const cupedPreExperimentStd =
    cupedPreExperimentStdRaw === "" ||
    cupedPreExperimentStdRaw === null ||
    cupedPreExperimentStdRaw === undefined
      ? null
      : Number(cupedPreExperimentStdRaw);
  const cupedCorrelationRaw = state.metrics.cuped_correlation;
  const cupedCorrelation =
    cupedCorrelationRaw === "" ||
    cupedCorrelationRaw === null ||
    cupedCorrelationRaw === undefined
      ? null
      : Number(cupedCorrelationRaw);
  const guardrailMetrics = state.metrics.guardrail_metrics ?? [];

  if (!projectName) {
    issues.push("Project name is required.");
  }
  if (!changeDescription) {
    issues.push("Change description is required.");
  }
  if (!primaryMetricName) {
    issues.push("Primary metric name is required.");
  }
  if (!Number.isInteger(variantsCount) || variantsCount < 2 || variantsCount > 10) {
    issues.push("Variants count must be an integer between 2 and 10.");
  }
  if (trafficSplit.length < 2) {
    issues.push("Traffic split must contain at least two positive weights.");
  } else if (Number.isInteger(variantsCount) && trafficSplit.length !== variantsCount) {
    issues.push("Traffic split length must match variants count.");
  }
  if (!(expectedDailyTraffic > 0)) {
    issues.push("Expected daily traffic must be greater than 0.");
  }
  if (!(audienceShareInTest > 0 && audienceShareInTest <= 1)) {
    issues.push("Audience share in test must be between 0 and 1.");
  }
  if (!(mdePct > 0)) {
    issues.push("MDE % must be greater than 0.");
  }
  if (analysisMode === "bayesian") {
    if (!(desiredPrecision !== null && desiredPrecision > 0)) {
      issues.push("Desired precision must be greater than 0 in Bayesian mode.");
    }
    if (!(credibility > 0.5 && credibility < 1)) {
      issues.push("Credibility must be between 0.5 and 1.");
    }
  } else {
    if (!(alpha > 0 && alpha < 1)) {
      issues.push("Alpha must be between 0 and 1.");
    }
    if (!(power > 0 && power < 1)) {
      issues.push("Power must be between 0 and 1.");
    }
  }

  if (metricType === "binary") {
    if (!(baselineValue > 0 && baselineValue < 1)) {
      issues.push("Binary baseline value must be between 0 and 1.");
    }
  } else if (metricType === "continuous") {
    if (!(baselineValue > 0)) {
      issues.push("Continuous baseline value must be greater than 0.");
    }
    if (stdDev === null || !(stdDev > 0)) {
      issues.push("Continuous metrics require a positive std dev.");
    }
    if (cupedEnabled) {
      if (cupedPreExperimentStd === null || !(cupedPreExperimentStd > 0)) {
        issues.push("CUPED pre-experiment std dev must be positive.");
      }
      if (cupedCorrelation === null || !(cupedCorrelation > -1 && cupedCorrelation < 1)) {
        issues.push("CUPED correlation must be between -1 and 1.");
      }
    }
  } else {
    issues.push("Metric type must be either binary or continuous.");
  }

  if (guardrailMetrics.length > 3) {
    issues.push("Guardrail metrics cannot exceed 3 items.");
  }

  for (const guardrail of guardrailMetrics) {
    if (!String(guardrail.name ?? "").trim()) {
      issues.push("Guardrail metric names are required.");
      break;
    }

    if (guardrail.metric_type === "binary") {
      const baselineRate =
        guardrail.baseline_rate === "" || guardrail.baseline_rate === undefined
          ? Number.NaN
          : Number(guardrail.baseline_rate);

      if (!(baselineRate > 0 && baselineRate < 100)) {
        issues.push("Binary guardrails require a baseline % between 0 and 100.");
        break;
      }
      continue;
    }

    if (guardrail.metric_type === "continuous") {
      const baselineMean =
        guardrail.baseline_mean === "" || guardrail.baseline_mean === undefined
          ? Number.NaN
          : Number(guardrail.baseline_mean);
      const guardrailStdDev =
        guardrail.std_dev === "" || guardrail.std_dev === undefined
          ? Number.NaN
          : Number(guardrail.std_dev);

      if (Number.isNaN(baselineMean) || !(guardrailStdDev > 0)) {
        issues.push("Continuous guardrails require baseline mean and positive std dev.");
        break;
      }
      continue;
    }

    issues.push("Guardrail metric type must be either binary or continuous.");
    break;
  }

  return issues;
}

export function validateStep(step: number | WizardStepKey, draft: FullPayload): string[] {
  const stepKey = resolveStepKey(step);
  const issues = validateForm(draft);

  if (stepKey === "review") {
    return issues;
  }

  const prefixes = getStepPrefixes(stepKey);
  return issues.filter((issue) =>
    Object.entries(fieldIssueLookup).some(
      ([field, patterns]) =>
        prefixes.some((prefix) => field.startsWith(prefix)) &&
        patterns.includes(issue)
    )
  );
}

export function isStepValid(step: number | WizardStepKey, draft: FullPayload): boolean {
  return validateStep(step, draft).length === 0;
}

export function getFieldValidationMessage(
  section: FullPayloadSectionKey,
  key: string,
  issues: string[]
): string | null {
  const patterns = fieldIssueLookup[`${String(section)}.${key}`];
  if (!patterns) {
    return null;
  }

  return issues.find((issue) => patterns.includes(issue)) ?? null;
}

export function validateField(
  state: FullPayload,
  section: FullPayloadSectionKey,
  key: string
): string | null {
  return getFieldValidationMessage(section, key, validateForm(state));
}
