import { getSectionFieldValue } from "./payload";
import type {
  FieldDef,
  FullPayload,
  ReviewSection,
  SectionConfig,
  SelectOption,
  WizardStep
} from "./types";

export const stepLabels = ["Project", "Hypothesis", "Setup", "Metrics", "Constraints", "Review"] as const;
export const FIELD_TOOLTIPS: Record<string, string> = {
  traffic_split:
    "Relative traffic weights per variant. Example: 50,50 for a balanced A/B split or 34,33,33 for three variants.",
  expected_daily_traffic:
    "Average number of users or sessions entering the experiment each day. Example: 12000.",
  audience_share_in_test:
    "Share of daily traffic that is eligible for the test. Use 0.6 for 60% of incoming traffic.",
  variants_count:
    "Total number of variants including control. 2 = a classic A/B test, while 3+ variants increase sample needs.",
  baseline_value:
    "Current baseline metric. For binary metrics use 0.042 for 4.2%; for continuous metrics use the current mean, such as 45.20; for ratio metrics use the baseline ratio R, such as 0.05 for a 5% click-through rate; for count / rate metrics use the baseline event rate per exposure unit, such as 0.30 for 0.3 events per user.",
  exposure_per_user:
    "Count / rate metrics only: how much exposure one user contributes over the experiment (sessions, device-days, ...). Leave empty or use 1 when the user itself is the exposure unit; the required sample size scales inversely with this.",
  expected_uplift_pct:
    "Expected relative improvement versus baseline. Example: 8 means the treatment is expected to improve the metric by 8%. This is planning context only and does not change the required sample size.",
  mde_pct:
    "Minimum detectable effect as a percent of baseline. Smaller MDE values require larger sample sizes. Sample size and duration are driven by this MDE, not by the expected uplift.",
  alpha:
    "False-positive threshold. 0.05 means accepting a 5% probability of a Type I error.",
  power:
    "Probability of detecting a real effect if it exists. 0.8 is the standard minimum for product experiments.",
  analysis_mode:
    "Choose whether planning is framed with classic NHST power or Bayesian credible-interval precision.",
  desired_precision:
    "Target half-width of the credible interval. For binary metrics use percentage points; for continuous metrics use raw units.",
  credibility:
    "Credibility level for the Bayesian interval. 0.95 corresponds to a 95% credible interval.",
  std_dev:
    "Standard deviation per randomization unit. Required for continuous metrics (e.g. 12.5 for average order value) and for ratio metrics, where it is the per-user delta-method linearized standard deviation used to plan the sample size.",
  numerator_metric_name:
    "Numerator event for a ratio metric (e.g. clicks for click-through rate). Ingest it as a conversion metric of this name; the live delta-method test reads it per user.",
  denominator_metric_name:
    "Denominator event for a ratio metric (e.g. impressions for click-through rate). Ingest it as a separate conversion metric; the ratio is sum(numerator)/sum(denominator) per arm.",
  holdout_fraction:
    "Global holdout: share of traffic kept out of every experiment as a clean control. Leave empty for none, or use 0.1 for a 10% holdout. Reduces the traffic this test receives, so the duration grows; sample size is unchanged.",
  mutually_exclusive_experiments:
    "Number of mutually-exclusive experiments sharing the same traffic. Leave empty for 1. With N, this test gets 1/N of the traffic, extending the duration accordingly.",
  planned_test:
    "Analysis method the sample size is planned for. The z-test plan is the classic default; Fisher's exact needs slightly more users on small samples; Mann-Whitney (rank test, for skewed metrics) inflates the plan by ~5%; equivalence (TOST) plans to CONFIRM the arms are the same within a margin instead of detecting a difference.",
  equivalence_margin_pct:
    "Symmetric equivalence margin as a percent of baseline: the largest difference still treated as 'practically the same'. Drives the TOST sample size (the MDE does not apply to an equivalence plan)."
};

export const WIZARD_STEPS: WizardStep[] = [
  { key: "project", label: stepLabels[0] },
  { key: "hypothesis", label: stepLabels[1] },
  { key: "setup", label: stepLabels[2] },
  { key: "metrics", label: stepLabels[3] },
  { key: "constraints", label: stepLabels[4] },
  { key: "review", label: stepLabels[5] }
];

export const sections: SectionConfig[] = [
  {
    title: "Project context",
    section: "project",
    fields: [
      { label: "Project name", key: "project_name" },
      { label: "Domain", key: "domain" },
      { label: "Product type", key: "product_type" },
      { label: "Platform", key: "platform" },
      { label: "Market", key: "market" },
      { label: "Project description", key: "project_description", kind: "textarea", fullWidth: true }
    ]
  },
  {
    title: "Hypothesis",
    section: "hypothesis",
    fields: [
      { label: "Change description", key: "change_description", fullWidth: true },
      { label: "Target audience", key: "target_audience" },
      { label: "Business problem", key: "business_problem" },
      { label: "Hypothesis statement", key: "hypothesis_statement", kind: "textarea", fullWidth: true },
      { label: "What to validate", key: "what_to_validate" },
      { label: "Desired result", key: "desired_result" }
    ]
  },
  {
    title: "Experiment setup",
    section: "setup",
    fields: [
      { label: "Experiment type", key: "experiment_type" },
      {
        label: "Randomization unit",
        key: "randomization_unit",
        options: [
          { label: "User", value: "user" },
          { label: "Session", value: "session" },
          { label: "Device", value: "device" },
          { label: "Account", value: "account" },
          { label: "Cluster (store, region, classroom)", value: "cluster" }
        ]
      },
      {
        label: "Traffic split",
        key: "traffic_split",
        helpText: FIELD_TOOLTIPS.traffic_split
      },
      {
        label: "Expected daily traffic",
        key: "expected_daily_traffic",
        kind: "number",
        helpText: FIELD_TOOLTIPS.expected_daily_traffic
      },
      {
        label: "Audience share in test",
        key: "audience_share_in_test",
        kind: "number",
        helpText: FIELD_TOOLTIPS.audience_share_in_test
      },
      {
        label: "Variants count",
        key: "variants_count",
        kind: "number",
        helpText: FIELD_TOOLTIPS.variants_count
      },
      { label: "Inclusion criteria", key: "inclusion_criteria" },
      { label: "Exclusion criteria", key: "exclusion_criteria" }
    ]
  },
  {
    title: "Metrics",
    section: "metrics",
    fields: [
      { label: "Primary metric", key: "primary_metric_name" },
      {
        label: "Metric type",
        key: "metric_type",
        options: [
          { label: "Binary", value: "binary" },
          { label: "Continuous", value: "continuous" },
          { label: "Ratio", value: "ratio" },
          { label: "Count / rate", value: "count" }
        ]
      },
      {
        label: "Baseline value",
        key: "baseline_value",
        kind: "number",
        helpText: FIELD_TOOLTIPS.baseline_value
      },
      {
        label: "Exposure per user",
        key: "exposure_per_user",
        kind: "number",
        emptyValue: "",
        visibleWhen: (state) => state.metrics.metric_type === "count",
        helpText: FIELD_TOOLTIPS.exposure_per_user
      },
      {
        label: "Expected uplift %",
        key: "expected_uplift_pct",
        kind: "number",
        emptyValue: null,
        helpText: FIELD_TOOLTIPS.expected_uplift_pct
      },
      {
        label: "MDE %",
        key: "mde_pct",
        kind: "number",
        helpText: FIELD_TOOLTIPS.mde_pct
      },
      {
        label: "Std dev",
        key: "std_dev",
        kind: "number",
        emptyValue: "",
        visibleWhen: (state) =>
          state.metrics.metric_type === "continuous" || state.metrics.metric_type === "ratio",
        helpText: FIELD_TOOLTIPS.std_dev
      },
      // Planned analysis method: the option set is metric-type specific, so the field is declared
      // twice with mutually exclusive visibility (the generic select renders whichever applies).
      {
        label: "Planned analysis",
        key: "planned_test",
        options: [
          { label: "z-test (default)", value: "z_test" },
          { label: "Fisher's exact (small samples)", value: "fisher_exact" }
        ],
        visibleWhen: (state) => state.metrics.metric_type === "binary",
        helpText: FIELD_TOOLTIPS.planned_test
      },
      {
        label: "Planned analysis",
        key: "planned_test",
        options: [
          { label: "z-test (default)", value: "z_test" },
          { label: "Mann-Whitney (rank test)", value: "mann_whitney" },
          { label: "Equivalence (TOST)", value: "tost" }
        ],
        visibleWhen: (state) => state.metrics.metric_type === "continuous",
        helpText: FIELD_TOOLTIPS.planned_test
      },
      {
        label: "Equivalence margin %",
        key: "equivalence_margin_pct",
        kind: "number",
        emptyValue: "",
        visibleWhen: (state) =>
          state.metrics.metric_type === "continuous" && state.metrics.planned_test === "tost",
        helpText: FIELD_TOOLTIPS.equivalence_margin_pct
      },
      {
        label: "Numerator metric",
        key: "numerator_metric_name",
        visibleWhen: (state) => state.metrics.metric_type === "ratio",
        helpText: FIELD_TOOLTIPS.numerator_metric_name
      },
      {
        label: "Denominator metric",
        key: "denominator_metric_name",
        visibleWhen: (state) => state.metrics.metric_type === "ratio",
        helpText: FIELD_TOOLTIPS.denominator_metric_name
      },
      { label: "Secondary metrics", key: "secondary_metrics", kind: "textarea", fullWidth: true },
      { label: "Guardrail metrics", key: "guardrail_metrics", kind: "textarea", fullWidth: true }
    ]
  },
  {
    title: "Constraints",
    section: "constraints",
    fields: [
      { label: "Seasonality present", key: "seasonality_present", kind: "boolean" },
      { label: "Active campaigns present", key: "active_campaigns_present", kind: "boolean" },
      { label: "Returning users present", key: "returning_users_present", kind: "boolean" },
      {
        label: "Analysis framework",
        key: "analysis_mode",
        helpText: FIELD_TOOLTIPS.analysis_mode
      },
      {
        label: "Alpha",
        key: "alpha",
        section: "metrics",
        kind: "number",
        visibleWhen: (state) => (state.constraints.analysis_mode ?? "frequentist") === "frequentist",
        helpText: FIELD_TOOLTIPS.alpha
      },
      {
        label: "Power",
        key: "power",
        section: "metrics",
        kind: "number",
        visibleWhen: (state) => (state.constraints.analysis_mode ?? "frequentist") === "frequentist",
        helpText: FIELD_TOOLTIPS.power
      },
      {
        label: "Desired precision",
        key: "desired_precision",
        kind: "number",
        emptyValue: null,
        visibleWhen: (state) => state.constraints.analysis_mode === "bayesian",
        helpText: FIELD_TOOLTIPS.desired_precision
      },
      {
        label: "Credibility",
        key: "credibility",
        kind: "number",
        visibleWhen: (state) => state.constraints.analysis_mode === "bayesian",
        helpText: FIELD_TOOLTIPS.credibility
      },
      {
        label: "Holdout fraction",
        key: "holdout_fraction",
        kind: "number",
        emptyValue: null,
        helpText: FIELD_TOOLTIPS.holdout_fraction
      },
      {
        label: "Mutually exclusive experiments",
        key: "mutually_exclusive_experiments",
        kind: "number",
        emptyValue: null,
        helpText: FIELD_TOOLTIPS.mutually_exclusive_experiments
      },
      {
        label: "Interference risk",
        key: "interference_risk",
        helpText: "Risk that users or units can influence one another across variants and break isolation.",
        options: [
          { label: "Low", value: "low" },
          { label: "Medium", value: "medium" },
          { label: "High", value: "high" }
        ]
      },
      { label: "Technical constraints", key: "technical_constraints", fullWidth: true },
      { label: "Legal / ethics constraints", key: "legal_or_ethics_constraints", fullWidth: true },
      { label: "Known risks", key: "known_risks", fullWidth: true },
      {
        label: "Deadline pressure",
        key: "deadline_pressure",
        options: [
          { label: "Low", value: "low" },
          { label: "Medium", value: "medium" },
          { label: "High", value: "high" }
        ]
      },
      { label: "Long test possible", key: "long_test_possible", kind: "boolean" },
      {
        label: "AI context",
        key: "llm_context",
        kind: "textarea",
        section: "additional_context",
        fullWidth: true
      }
    ]
  }
];

export const REVIEW_SECTIONS = sections;
export const FIELD_DEFINITIONS: Record<string, FieldDef> = sections.reduce<Record<string, FieldDef>>((lookup, section) => {
  section.fields.forEach((field) => {
    lookup[`${String(field.section ?? section.section)}.${field.key}`] = field;
  });
  return lookup;
}, {});

export function formatReviewValue(value: unknown, options?: SelectOption[]): string {
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (options && options.length > 0) {
    const normalized = String(value ?? "").trim();
    const match = options.find((option) => option.value === normalized);
    if (match) {
      return match.label;
    }
  }
  if (Array.isArray(value)) {
    if (
      value.every(
        (item) =>
          typeof item === "object" &&
          item !== null &&
          "name" in item &&
          "metric_type" in item
      )
    ) {
      return value
        .map((item) => {
          if (typeof item !== "object" || item === null || !("name" in item) || !("metric_type" in item)) {
            return "";
          }

          const name = typeof item.name === "string" ? item.name : "";
          const metricType = typeof item.metric_type === "string" ? item.metric_type : "";
          const baselineRate =
            "baseline_rate" in item && (typeof item.baseline_rate === "number" || item.baseline_rate === "")
              ? item.baseline_rate
              : undefined;
          const baselineMean =
            "baseline_mean" in item && (typeof item.baseline_mean === "number" || item.baseline_mean === "")
              ? item.baseline_mean
              : undefined;
          const stdDev =
            "std_dev" in item && (typeof item.std_dev === "number" || item.std_dev === "")
              ? item.std_dev
              : undefined;

          if (metricType === "binary") {
            return `${name} (binary, baseline ${String(baselineRate ?? "-")}%)`;
          }

          return (
            `${name} (continuous, mean ${String(baselineMean ?? "-")}, ` +
            `std dev ${String(stdDev ?? "-")})`
          );
        })
        .filter((item) => item.length > 0)
        .join("; ");
    }

    return value.join(", ");
  }

  const normalized = String(value ?? "").trim();
  return normalized.length > 0 ? normalized : "-";
}

export function getReviewSections(state: FullPayload): ReviewSection[] {
  return REVIEW_SECTIONS.map((section) => ({
    title: section.title,
    section: section.section,
    items: section.fields
      .filter((field) => (field.visibleWhen ? field.visibleWhen(state) : true))
      .map((field) => {
        const targetSection = field.section ?? section.section;
        const rawValue = getSectionFieldValue(state, targetSection, field.key);
        return {
          label: field.label,
          value: formatReviewValue(rawValue, field.options),
          section: targetSection,
          key: field.key,
          rawValue,
          options: field.options
        };
      })
  }));
}
