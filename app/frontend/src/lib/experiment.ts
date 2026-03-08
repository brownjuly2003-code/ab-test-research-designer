export type MetricType = "binary" | "continuous";

export type ProjectSection = {
  project_name: string;
  domain: string;
  product_type: string;
  platform: string;
  market: string;
  project_description: string;
};

export type HypothesisSection = {
  change_description: string;
  target_audience: string;
  business_problem: string;
  hypothesis_statement: string;
  what_to_validate: string;
  desired_result: string;
};

export type SetupDraftSection = {
  experiment_type: string;
  randomization_unit: string;
  traffic_split: string;
  expected_daily_traffic: number;
  audience_share_in_test: number;
  variants_count: number;
  inclusion_criteria: string;
  exclusion_criteria: string;
};

export type SetupPayloadSection = Omit<SetupDraftSection, "traffic_split"> & {
  traffic_split: number[];
};

export type MetricsDraftSection = {
  primary_metric_name: string;
  metric_type: MetricType;
  baseline_value: number;
  expected_uplift_pct: number | null;
  mde_pct: number;
  alpha: number;
  power: number;
  std_dev: number | "";
  secondary_metrics: string;
  guardrail_metrics: string;
};

export type MetricsPayloadSection = Omit<
  MetricsDraftSection,
  "std_dev" | "secondary_metrics" | "guardrail_metrics"
> & {
  std_dev: number | null;
  secondary_metrics: string[];
  guardrail_metrics: string[];
};

export type ConstraintsSection = {
  seasonality_present: boolean;
  active_campaigns_present: boolean;
  returning_users_present: boolean;
  interference_risk: string;
  technical_constraints: string;
  legal_or_ethics_constraints: string;
  known_risks: string;
  deadline_pressure: string;
  long_test_possible: boolean;
};

export type AdditionalContextSection = {
  llm_context: string;
};

export type FullPayload = {
  project: ProjectSection;
  hypothesis: HypothesisSection;
  setup: SetupDraftSection;
  metrics: MetricsDraftSection;
  constraints: ConstraintsSection;
  additional_context: AdditionalContextSection;
};

export type ExperimentInputPayload = {
  project: ProjectSection;
  hypothesis: HypothesisSection;
  setup: SetupPayloadSection;
  metrics: MetricsPayloadSection;
  constraints: ConstraintsSection;
  additional_context: AdditionalContextSection;
};

export type LoadedPayload = {
  project: ProjectSection;
  hypothesis: HypothesisSection;
  setup: Omit<SetupDraftSection, "traffic_split"> & {
    traffic_split: string | number[];
  };
  metrics: Omit<MetricsDraftSection, "std_dev" | "secondary_metrics" | "guardrail_metrics"> & {
    std_dev: number | "" | null;
    secondary_metrics: string | string[];
    guardrail_metrics: string | string[];
  };
  constraints: ConstraintsSection;
  additional_context: AdditionalContextSection;
};

export type CalculationRequestPayload = {
  metric_type: MetricType;
  baseline_value: number;
  std_dev: number | null;
  mde_pct: number;
  alpha: number;
  power: number;
  expected_daily_traffic: number;
  audience_share_in_test: number;
  traffic_split: number[];
  variants_count: number;
  seasonality_present: boolean;
  active_campaigns_present: boolean;
  long_test_possible: boolean;
};

export type ApiErrorResponse = {
  detail?: string;
};

export type WarningItem = {
  code: string;
  message: string;
  severity: string;
  source?: string;
};

export type CalculationSummary = {
  metric_type: MetricType;
  baseline_value: number;
  mde_pct: number;
  mde_absolute: number;
  alpha: number;
  power: number;
};

export type CalculationResponse = {
  calculation_summary: CalculationSummary;
  results: {
    sample_size_per_variant: number;
    total_sample_size: number;
    effective_daily_traffic: number;
    estimated_duration_days: number;
  };
  assumptions: string[];
  warnings: WarningItem[];
};

export type ReportResponse = {
  executive_summary: string;
  calculations: {
    sample_size_per_variant: number;
    total_sample_size: number;
    estimated_duration_days: number;
    assumptions: string[];
  };
  experiment_design: {
    variants: {
      name: string;
      description: string;
    }[];
    randomization_unit: string;
    traffic_split: number[];
    target_audience: string;
    inclusion_criteria: string;
    exclusion_criteria: string;
    recommended_duration_days: number;
    stopping_conditions: string[];
  };
  metrics_plan: {
    primary: string[];
    secondary: string[];
    guardrail: string[];
    diagnostic: string[];
  };
  risks: {
    statistical: string[];
    product: string[];
    technical: string[];
    operational: string[];
  };
  recommendations: {
    before_launch: string[];
    during_test: string[];
    after_test: string[];
  };
  open_questions: string[];
};

export type AdvicePayload = {
  brief_assessment: string;
  key_risks: string[];
  design_improvements: string[];
  metric_recommendations: string[];
  interpretation_pitfalls: string[];
  additional_checks: string[];
};

export type AdviceResponse = {
  available: boolean;
  provider: string;
  model: string;
  advice: AdvicePayload | null;
  raw_text: string | null;
  error: string | null;
  error_code: string | null;
};

export type ProjectActivityMeta = {
  payload_schema_version?: number;
  last_analysis_at?: string | null;
  last_analysis_run_id?: string | null;
  last_exported_at?: string | null;
  has_analysis_snapshot?: boolean;
};

export type AnalysisRunSummary = {
  metric_type?: string | null;
  sample_size_per_variant?: number | null;
  total_sample_size?: number | null;
  estimated_duration_days?: number | null;
  warnings_count: number;
  advice_available: boolean;
};

export type ProjectAnalysisRun = {
  id: string;
  project_id: string;
  created_at: string;
  summary: AnalysisRunSummary;
  analysis: {
    calculations: CalculationResponse;
    report: ReportResponse;
    advice: AdviceResponse;
  };
};

export type ProjectExportEvent = {
  id: string;
  project_id: string;
  analysis_run_id: string | null;
  format: ExportFormat;
  created_at: string;
};

export type ProjectHistory = {
  project_id: string;
  analysis_runs: ProjectAnalysisRun[];
  export_events: ProjectExportEvent[];
};

export type ApiHealthResponse = {
  status: string;
  service: string;
  version: string;
  environment: string;
};

export type ResultsState = {
  calculations?: CalculationResponse;
  report?: ReportResponse;
  advice?: AdviceResponse;
};

export type SavedProject = ProjectActivityMeta & {
  id: string;
  project_name: string;
  created_at: string;
  updated_at: string;
};

export type ExportFormat = "markdown" | "html";
export type FieldKind = "text" | "textarea" | "number" | "boolean";
export type FullPayloadSectionKey = keyof FullPayload;
export type DraftFieldValue = string | number | boolean | null;
export type SelectOption = {
  label: string;
  value: string;
};
export type SectionField = {
  label: string;
  key: string;
  kind?: FieldKind;
  section?: FullPayloadSectionKey;
  fullWidth?: boolean;
  options?: SelectOption[];
  visibleWhen?: (state: FullPayload) => boolean;
  emptyValue?: number | "" | null;
};
export type SectionConfig = {
  title: string;
  section: FullPayloadSectionKey;
  fields: SectionField[];
};

export type ReviewItem = {
  label: string;
  value: string;
};

export type ReviewSection = {
  title: string;
  items: ReviewItem[];
};

export type DraftTransferFile = {
  schema_version: number;
  payload: ExperimentInputPayload;
};

export const browserDraftStorageKey = "ab-test-research-designer:draft:v1";

const configuredApiBase = import.meta.env.VITE_API_BASE_URL?.trim();
const apiBase =
  configuredApiBase && configuredApiBase.length > 0
    ? configuredApiBase.replace(/\/$/, "")
    : import.meta.env.DEV
      ? "http://127.0.0.1:8008"
      : "";

export function apiUrl(path: string): string {
  return `${apiBase}${path}`;
}

export const stepLabels = ["Project", "Hypothesis", "Setup", "Metrics", "Constraints", "Review"] as const;

export const initialState: FullPayload = {
  project: {
    project_name: "Checkout redesign",
    domain: "e-commerce",
    product_type: "web app",
    platform: "web",
    market: "US",
    project_description: "We want to test a simplified checkout flow."
  },
  hypothesis: {
    change_description: "Reduce checkout from 4 steps to 2",
    target_audience: "new users on web",
    business_problem: "checkout abandonment is high",
    hypothesis_statement: "If we simplify checkout, purchase conversion will increase because the flow becomes easier.",
    what_to_validate: "impact on conversion",
    desired_result: "statistically meaningful uplift"
  },
  setup: {
    experiment_type: "ab",
    randomization_unit: "user",
    traffic_split: "50,50",
    expected_daily_traffic: 12000,
    audience_share_in_test: 0.6,
    variants_count: 2,
    inclusion_criteria: "new users only",
    exclusion_criteria: "internal staff"
  },
  metrics: {
    primary_metric_name: "purchase_conversion",
    metric_type: "binary",
    baseline_value: 0.042,
    expected_uplift_pct: 8,
    mde_pct: 5,
    alpha: 0.05,
    power: 0.8,
    std_dev: "",
    secondary_metrics: "add_to_cart_rate",
    guardrail_metrics: "payment_error_rate, refund_rate"
  },
  constraints: {
    seasonality_present: true,
    active_campaigns_present: false,
    returning_users_present: true,
    interference_risk: "medium",
    technical_constraints: "legacy event logging",
    legal_or_ethics_constraints: "none",
    known_risks: "tracking quality",
    deadline_pressure: "medium",
    long_test_possible: true
  },
  additional_context: {
    llm_context: "Previous tests showed mixed results. Team worries about event quality and segmentation."
  }
};

export function cloneInitialState(): FullPayload {
  return structuredClone(initialState) as FullPayload;
}

type ImportedPayloadLike = {
  project: Record<string, unknown>;
  hypothesis: Record<string, unknown>;
  setup: Record<string, unknown>;
  metrics: Record<string, unknown>;
  constraints: Record<string, unknown>;
  additional_context?: Record<string, unknown>;
};

function readString<T extends object, K extends keyof T>(section: T, key: K): string {
  return String(section[key] ?? "").trim();
}

function readNumber<T extends object, K extends keyof T>(section: T, key: K): number {
  const value = section[key];
  return typeof value === "number" ? value : Number(value);
}

export function getSectionFieldValue(
  state: FullPayload,
  section: FullPayloadSectionKey,
  key: string
): unknown {
  return (state[section] as Record<string, unknown>)[key];
}

export function setSectionFieldValue(
  state: FullPayload,
  section: FullPayloadSectionKey,
  key: string,
  value: DraftFieldValue
): FullPayload {
  const nextState = {
    ...state,
    [section]: {
      ...(state[section] as Record<string, unknown>),
      [key]: value
    }
  } as FullPayload;

  if (section === "metrics" && key === "metric_type" && value === "binary") {
    return {
      ...nextState,
      metrics: {
        ...nextState.metrics,
        std_dev: ""
      }
    };
  }

  return nextState;
}

export function parseTrafficSplit(raw: unknown): number[] {
  if (Array.isArray(raw)) return raw.map(Number);
  return String(raw)
    .split(",")
    .map((value) => Number(value.trim()))
    .filter((value) => !Number.isNaN(value) && value > 0);
}

export function parseMetricList(raw: unknown): string[] {
  if (Array.isArray(raw)) {
    return raw.map((value) => String(value).trim()).filter((value) => value.length > 0);
  }

  return String(raw ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter((value) => value.length > 0);
}

export function buildApiPayload(state: FullPayload): ExperimentInputPayload {
  return {
    ...state,
    setup: {
      ...state.setup,
      traffic_split: parseTrafficSplit(state.setup.traffic_split)
    },
    metrics: {
      ...state.metrics,
      std_dev: state.metrics.std_dev === "" ? null : Number(state.metrics.std_dev),
      secondary_metrics: parseMetricList(state.metrics.secondary_metrics),
      guardrail_metrics: parseMetricList(state.metrics.guardrail_metrics)
    }
  };
}

export function buildCalculationPayload(state: FullPayload): CalculationRequestPayload {
  const payload = buildApiPayload(state);

  return {
    metric_type: payload.metrics.metric_type,
    baseline_value: payload.metrics.baseline_value,
    std_dev: payload.metrics.std_dev,
    mde_pct: payload.metrics.mde_pct,
    alpha: payload.metrics.alpha,
    power: payload.metrics.power,
    expected_daily_traffic: payload.setup.expected_daily_traffic,
    audience_share_in_test: payload.setup.audience_share_in_test,
    traffic_split: payload.setup.traffic_split,
    variants_count: payload.setup.variants_count,
    seasonality_present: payload.constraints.seasonality_present,
    active_campaigns_present: payload.constraints.active_campaigns_present,
    long_test_possible: payload.constraints.long_test_possible
  };
}

export function buildDraftTransferFile(state: FullPayload): DraftTransferFile {
  return {
    schema_version: 1,
    payload: buildApiPayload(state)
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasPayloadSections(value: unknown): value is ImportedPayloadLike {
  if (!isRecord(value)) {
    return false;
  }

  return ["project", "hypothesis", "setup", "metrics", "constraints"].every(
    (key) => isRecord(value[key])
  );
}

function normalizeImportedPayload(payload: ImportedPayloadLike): LoadedPayload {
  return {
    project: {
      ...initialState.project,
      ...payload.project
    },
    hypothesis: {
      ...initialState.hypothesis,
      ...payload.hypothesis
    },
    setup: {
      ...initialState.setup,
      ...payload.setup
    } as LoadedPayload["setup"],
    metrics: {
      ...initialState.metrics,
      ...payload.metrics
    } as LoadedPayload["metrics"],
    constraints: {
      ...initialState.constraints,
      ...payload.constraints
    },
    additional_context: {
      ...initialState.additional_context,
      ...(isRecord(payload.additional_context) ? payload.additional_context : {})
    }
  };
}

export function parseImportedDraft(raw: string): FullPayload {
  let parsed: unknown;

  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error("Draft JSON is invalid.");
  }

  const directPayload = hasPayloadSections(parsed)
    ? parsed
    : isRecord(parsed) && hasPayloadSections(parsed.payload)
      ? parsed.payload
      : null;

  if (!directPayload) {
    throw new Error("Imported JSON does not match the experiment payload format.");
  }

  return hydrateLoadedPayload(normalizeImportedPayload(directPayload));
}

export function hydrateLoadedPayload(payload: LoadedPayload | ExperimentInputPayload): FullPayload {
  return {
    ...payload,
    setup: {
      ...payload.setup,
      traffic_split: Array.isArray(payload.setup.traffic_split)
        ? payload.setup.traffic_split.join(",")
        : String(payload.setup.traffic_split ?? "")
    },
    metrics: {
      ...payload.metrics,
      std_dev:
        payload.metrics.std_dev === null || payload.metrics.std_dev === undefined
          ? ""
          : Number(payload.metrics.std_dev),
      secondary_metrics: parseMetricList(payload.metrics.secondary_metrics).join(", "),
      guardrail_metrics: parseMetricList(payload.metrics.guardrail_metrics).join(", ")
    }
  };
}

export function formatReviewValue(value: unknown): string {
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (Array.isArray(value)) {
    return value.join(", ");
  }

  const normalized = String(value ?? "").trim();
  return normalized.length > 0 ? normalized : "-";
}

export function getReviewSections(state: FullPayload): ReviewSection[] {
  return sections.map((section) => ({
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
  const stdDevRaw = state.metrics.std_dev;
  const stdDev =
    stdDevRaw === "" || stdDevRaw === null || stdDevRaw === undefined ? null : Number(stdDevRaw);

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
  if (!(alpha > 0 && alpha < 1)) {
    issues.push("Alpha must be between 0 and 1.");
  }
  if (!(power > 0 && power < 1)) {
    issues.push("Power must be between 0 and 1.");
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
  } else {
    issues.push("Metric type must be either binary or continuous.");
  }

  return issues;
}

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
      { label: "Traffic split", key: "traffic_split" },
      { label: "Expected daily traffic", key: "expected_daily_traffic", kind: "number" },
      { label: "Audience share in test", key: "audience_share_in_test", kind: "number" },
      { label: "Variants count", key: "variants_count", kind: "number" },
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
      { label: "Baseline value", key: "baseline_value", kind: "number" },
      { label: "Expected uplift %", key: "expected_uplift_pct", kind: "number", emptyValue: null },
      { label: "MDE %", key: "mde_pct", kind: "number" },
      { label: "Alpha", key: "alpha", kind: "number" },
      { label: "Power", key: "power", kind: "number" },
      {
        label: "Std dev",
        key: "std_dev",
        kind: "number",
        emptyValue: "",
        visibleWhen: (state) => state.metrics.metric_type === "continuous"
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
        label: "Interference risk",
        key: "interference_risk",
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
