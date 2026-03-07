export type FullPayload = {
  project: Record<string, unknown>;
  hypothesis: Record<string, unknown>;
  setup: Record<string, unknown>;
  metrics: Record<string, unknown>;
  constraints: Record<string, unknown>;
  additional_context: Record<string, unknown>;
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

export type CalculationResponse = {
  calculation_summary: Record<string, unknown>;
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

export type SavedProject = {
  id: string;
  project_name: string;
  created_at: string;
  updated_at: string;
};

export type ExportFormat = "markdown" | "html";
export type FieldKind = "text" | "textarea" | "number" | "boolean";
export type SectionField =
  | [string, string]
  | [string, string, FieldKind]
  | [string, string, FieldKind, keyof FullPayload];
export type SectionConfig = {
  title: string;
  section: keyof FullPayload;
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
  payload: FullPayload;
};

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

export const stepLabels = ["Project", "Hypothesis", "Setup", "Metrics", "Constraints", "Review"];

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

function readString(section: Record<string, unknown>, key: string): string {
  return String(section[key] ?? "").trim();
}

function readNumber(section: Record<string, unknown>, key: string): number {
  const value = section[key];
  return typeof value === "number" ? value : Number(value);
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

export function buildApiPayload(state: FullPayload): FullPayload {
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

export function buildCalculationPayload(state: FullPayload): Record<string, unknown> {
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

function hasPayloadSections(value: unknown): value is FullPayload {
  if (!isRecord(value)) {
    return false;
  }

  return ["project", "hypothesis", "setup", "metrics", "constraints"].every(
    (key) => isRecord(value[key])
  );
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

  return hydrateLoadedPayload({
    ...directPayload,
    additional_context: isRecord(directPayload.additional_context) ? directPayload.additional_context : {}
  });
}

export function hydrateLoadedPayload(payload: FullPayload): FullPayload {
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
          : String(payload.metrics.std_dev),
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
    items: section.fields.map(([label, key, _kind, explicitSection]) => {
      const targetSection = explicitSection ?? section.section;
      return {
        label,
        value: formatReviewValue(state[targetSection][key])
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
  if (!Number.isInteger(variantsCount) || variantsCount < 2) {
    issues.push("Variants count must be an integer greater than or equal to 2.");
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
      ["Project name", "project_name"],
      ["Domain", "domain"],
      ["Product type", "product_type"],
      ["Platform", "platform"],
      ["Market", "market"],
      ["Project description", "project_description", "textarea"]
    ]
  },
  {
    title: "Hypothesis",
    section: "hypothesis",
    fields: [
      ["Change description", "change_description"],
      ["Target audience", "target_audience"],
      ["Business problem", "business_problem"],
      ["Hypothesis statement", "hypothesis_statement", "textarea"],
      ["What to validate", "what_to_validate"],
      ["Desired result", "desired_result"]
    ]
  },
  {
    title: "Experiment setup",
    section: "setup",
    fields: [
      ["Experiment type", "experiment_type"],
      ["Randomization unit", "randomization_unit"],
      ["Traffic split", "traffic_split"],
      ["Expected daily traffic", "expected_daily_traffic", "number"],
      ["Audience share in test", "audience_share_in_test", "number"],
      ["Variants count", "variants_count", "number"],
      ["Inclusion criteria", "inclusion_criteria"],
      ["Exclusion criteria", "exclusion_criteria"]
    ]
  },
  {
    title: "Metrics",
    section: "metrics",
    fields: [
      ["Primary metric", "primary_metric_name"],
      ["Metric type", "metric_type"],
      ["Baseline value", "baseline_value", "number"],
      ["Expected uplift %", "expected_uplift_pct", "number"],
      ["MDE %", "mde_pct", "number"],
      ["Alpha", "alpha", "number"],
      ["Power", "power", "number"],
      ["Std dev", "std_dev", "number"],
      ["Secondary metrics", "secondary_metrics", "textarea"],
      ["Guardrail metrics", "guardrail_metrics", "textarea"]
    ]
  },
  {
    title: "Constraints",
    section: "constraints",
    fields: [
      ["Seasonality present", "seasonality_present", "boolean"],
      ["Active campaigns present", "active_campaigns_present", "boolean"],
      ["Returning users present", "returning_users_present", "boolean"],
      ["Interference risk", "interference_risk"],
      ["Technical constraints", "technical_constraints"],
      ["Legal / ethics constraints", "legal_or_ethics_constraints"],
      ["Known risks", "known_risks"],
      ["Deadline pressure", "deadline_pressure"],
      ["Long test possible", "long_test_possible", "boolean"],
      ["AI context", "llm_context", "textarea", "additional_context"]
    ]
  }
];
