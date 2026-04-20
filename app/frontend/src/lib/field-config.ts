import { getSectionFieldValue } from "./payload";
import type {
  FieldDef,
  FullPayload,
  ReviewSection,
  SectionConfig,
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
    "Current baseline metric. For binary metrics use 0.042 for 4.2%; for continuous metrics use the current mean, such as 45.20.",
  expected_uplift_pct:
    "Expected relative improvement versus baseline. Example: 8 means the treatment is expected to improve the metric by 8%.",
  mde_pct:
    "Minimum detectable effect as a percent of baseline. Smaller MDE values require larger sample sizes.",
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
    "Standard deviation of the continuous metric. Required only for continuous metrics; example: 12.5 for average order value."
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
          { label: "Account", value: "account" }
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
          { label: "Continuous", value: "continuous" }
        ]
      },
      {
        label: "Baseline value",
        key: "baseline_value",
        kind: "number",
        helpText: FIELD_TOOLTIPS.baseline_value
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
        visibleWhen: (state) => state.metrics.metric_type === "continuous",
        helpText: FIELD_TOOLTIPS.std_dev
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

export function formatReviewValue(value: unknown): string {
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
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
    items: section.fields
      .filter((field) => (field.visibleWhen ? field.visibleWhen(state) : true))
      .map((field) => {
        const targetSection = field.section ?? section.section;
        return {
          label: field.label,
          value: formatReviewValue(getSectionFieldValue(state, targetSection, field.key))
        };
      })
  }));
}
