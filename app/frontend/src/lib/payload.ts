import type {
  AdditionalContextSection,
  CalculateRequest,
  DesignRequest,
  DraftFieldValue,
  DraftTransferFile,
  ExperimentInputPayload,
  ExportRequest,
  FullPayload,
  FullPayloadSectionKey,
  HydratableExperimentInput,
  LoadedPayload
} from "./types";

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
    exclusion_criteria: "internal staff",
    avg_cluster_size: null,
    icc: null
  },
  metrics: {
    primary_metric_name: "purchase_conversion",
    metric_type: "binary",
    baseline_value: 0.042,
    expected_uplift_pct: 8,
    mde_pct: 5,
    alpha: 0.05,
    power: 0.8,
    numerator_metric_name: "",
    denominator_metric_name: "",
    std_dev: "",
    exposure_per_user: "",
    cuped_pre_experiment_std: "",
    cuped_correlation: "",
    cuped_enabled: false,
    planned_test: "z_test",
    equivalence_margin_pct: "",
    secondary_metrics: "add_to_cart_rate",
    guardrail_metrics: [
      {
        name: "Payment error rate",
        metric_type: "binary",
        baseline_rate: 2.4
      },
      {
        name: "Refund value",
        metric_type: "continuous",
        baseline_mean: 18,
        std_dev: 6.5
      }
    ]
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
    long_test_possible: true,
    n_looks: 1,
    analysis_mode: "frequentist",
    desired_precision: null,
    credibility: 0.95,
    holdout_fraction: null,
    mutually_exclusive_experiments: null
  },
  additional_context: {
    llm_context: "Previous tests showed mixed results. Team worries about event quality and segmentation."
  }
};

export function cloneInitialState(): FullPayload {
  return structuredClone(initialState);
}

type ImportedPayloadLike = {
  project: Partial<LoadedPayload["project"]>;
  hypothesis: Partial<LoadedPayload["hypothesis"]>;
  setup: Partial<LoadedPayload["setup"]>;
  metrics: Partial<LoadedPayload["metrics"]>;
  constraints: Partial<LoadedPayload["constraints"]>;
  additional_context?: Partial<LoadedPayload["additional_context"]>;
};

export function getSectionFieldValue(
  state: FullPayload,
  section: FullPayloadSectionKey,
  key: string
): unknown {
  return Reflect.get(state[section], key);
}

export function setSectionFieldValue(
  state: FullPayload,
  section: FullPayloadSectionKey,
  key: string,
  value: DraftFieldValue
): FullPayload {
  const nextState = structuredClone(state);
  Reflect.set(nextState[section], key, value);

  if (section === "setup" && key === "randomization_unit" && value !== "cluster") {
    // The average cluster size and ICC only size a cluster design; clear them when the unit is not a
    // cluster so a stale value never leaks into a non-cluster plan (mirrors the exposure_per_user reset).
    nextState.setup.avg_cluster_size = null;
    nextState.setup.icc = null;
  }

  if (section === "metrics" && key === "metric_type") {
    // The planned analysis method is metric-type specific (z/Fisher for binary, z/MW/TOST for
    // continuous), so switching the metric type falls back to the default z plan. The per-user
    // exposure only means something for count metrics, so it resets on every metric-type change.
    nextState.metrics.planned_test = "z_test";
    nextState.metrics.equivalence_margin_pct = "";
    nextState.metrics.exposure_per_user = "";
    // Binary and count metrics have no std dev / CUPED companion, so those fields are cleared when
    // switching to either.
    if (value === "binary" || value === "count") {
      return {
        ...nextState,
        metrics: {
          ...nextState.metrics,
          std_dev: "",
          cuped_pre_experiment_std: "",
          cuped_correlation: "",
          cuped_enabled: false
        }
      };
    }
  }

  return nextState;
}

export function parseTrafficSplit(raw: unknown): number[] {
  if (Array.isArray(raw)) {
    return raw.map(Number);
  }

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
  const {
    std_dev,
    exposure_per_user,
    cuped_pre_experiment_std,
    cuped_correlation,
    cuped_enabled,
    equivalence_margin_pct,
    secondary_metrics,
    guardrail_metrics,
    ...metrics
  } = state.metrics;

  return {
    ...state,
    setup: {
      ...state.setup,
      traffic_split: parseTrafficSplit(state.setup.traffic_split)
    },
    metrics: {
      ...metrics,
      std_dev: std_dev === "" ? null : Number(std_dev),
      // Per-user exposure only sizes count metrics; an empty field means "the user is the exposure
      // unit" (the backend defaults it to 1.0).
      exposure_per_user: exposure_per_user === "" ? null : Number(exposure_per_user),
      // The margin only means something for a TOST equivalence plan; a stale value left over from
      // a previous selection must not leak into the payload.
      equivalence_margin_pct:
        metrics.planned_test === "tost" && equivalence_margin_pct !== ""
          ? Number(equivalence_margin_pct)
          : null,
      cuped_pre_experiment_std:
        cuped_enabled && cuped_pre_experiment_std !== ""
          ? Number(cuped_pre_experiment_std)
          : null,
      cuped_correlation:
        cuped_enabled && cuped_correlation !== ""
          ? Number(cuped_correlation)
          : null,
      secondary_metrics: parseMetricList(secondary_metrics),
      guardrail_metrics: guardrail_metrics.map((guardrail) => {
        const direction = guardrail.direction ?? "increase_is_bad";
        const non_inferiority_margin_pct =
          guardrail.non_inferiority_margin_pct === "" || guardrail.non_inferiority_margin_pct === undefined
            ? undefined
            : Number(guardrail.non_inferiority_margin_pct);
        return guardrail.metric_type === "binary"
          ? {
              name: guardrail.name,
              metric_type: "binary" as const,
              baseline_rate:
                guardrail.baseline_rate === "" || guardrail.baseline_rate === undefined
                  ? undefined
                  : Number(guardrail.baseline_rate),
              direction,
              non_inferiority_margin_pct
            }
          : {
              name: guardrail.name,
              metric_type: "continuous" as const,
              baseline_mean:
                guardrail.baseline_mean === "" || guardrail.baseline_mean === undefined
                  ? undefined
                  : Number(guardrail.baseline_mean),
              std_dev:
                guardrail.std_dev === "" || guardrail.std_dev === undefined
                  ? undefined
                  : Number(guardrail.std_dev),
              direction,
              non_inferiority_margin_pct
            };
      })
    }
  };
}

export function buildAnalyzePayload(state: FullPayload): ExperimentInputPayload {
  return buildApiPayload(state);
}

export function buildCalculationPayload(state: FullPayload): CalculateRequest {
  const payload = buildApiPayload(state);

  // Ratio metrics are sized by the delta method (the per-user linearized value is treated as a
  // continuous metric with the supplied std_dev), so they flow through the planner like binary and
  // continuous. `canCompute` requires a positive baseline ratio and std_dev before this runs.
  const metricType = payload.metrics.metric_type;

  return {
    metric_type: metricType,
    baseline_value: payload.metrics.baseline_value,
    std_dev: payload.metrics.std_dev,
    exposure_per_user: payload.metrics.exposure_per_user,
    cuped_pre_experiment_std: payload.metrics.cuped_pre_experiment_std,
    cuped_correlation: payload.metrics.cuped_correlation,
    planned_test: payload.metrics.planned_test,
    equivalence_margin_pct: payload.metrics.equivalence_margin_pct,
    mde_pct: payload.metrics.mde_pct,
    alpha: payload.metrics.alpha,
    power: payload.metrics.power,
    expected_daily_traffic: payload.setup.expected_daily_traffic,
    audience_share_in_test: payload.setup.audience_share_in_test,
    traffic_split: payload.setup.traffic_split,
    variants_count: payload.setup.variants_count,
    randomization_unit: payload.setup.randomization_unit,
    avg_cluster_size: payload.setup.avg_cluster_size,
    icc: payload.setup.icc,
    seasonality_present: payload.constraints.seasonality_present,
    active_campaigns_present: payload.constraints.active_campaigns_present,
    long_test_possible: payload.constraints.long_test_possible,
    n_looks: payload.constraints.n_looks ?? 1,
    analysis_mode: payload.constraints.analysis_mode ?? "frequentist",
    desired_precision: payload.constraints.desired_precision ?? null,
    credibility: payload.constraints.credibility ?? 0.95,
    holdout_fraction: payload.constraints.holdout_fraction ?? null,
    mutually_exclusive_experiments: payload.constraints.mutually_exclusive_experiments ?? null
  };
}

export function buildCalculatePayload(state: FullPayload): CalculateRequest {
  return buildCalculationPayload(state);
}

export function buildDesignPayload(state: FullPayload): DesignRequest {
  return buildApiPayload(state);
}

export function buildExportPayload(result: ExportRequest): ExportRequest {
  return result;
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
  const setup: LoadedPayload["setup"] = {
    ...initialState.setup,
    ...payload.setup
  };
  const metrics: LoadedPayload["metrics"] = {
    ...initialState.metrics,
    ...payload.metrics
  };

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
      ...setup
    },
    metrics: {
      ...metrics
    },
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

export function hydrateLoadedPayload(
  payload: LoadedPayload | HydratableExperimentInput
): FullPayload {
  const observedResults = payload.additional_context?.observed_results;
  const normalizedObservedResults: AdditionalContextSection["observed_results"] = observedResults
    ? {
        ...observedResults,
        request: {
          ...observedResults.request,
          metric_type: observedResults.request.metric_type === "continuous" ? "continuous" : "binary"
        },
        analysis: {
          ...observedResults.analysis,
          metric_type: observedResults.analysis.metric_type === "continuous" ? "continuous" : "binary"
        }
      }
    : undefined;
  const additionalContext: AdditionalContextSection = payload.additional_context
    ? {
        ...payload.additional_context,
        observed_results: normalizedObservedResults
      }
    : { llm_context: "" };
  const cupedPreExperimentStd =
    payload.metrics.cuped_pre_experiment_std === "" || payload.metrics.cuped_pre_experiment_std === null || payload.metrics.cuped_pre_experiment_std === undefined
      ? ""
      : Number(payload.metrics.cuped_pre_experiment_std);
  const cupedCorrelation =
    payload.metrics.cuped_correlation === "" || payload.metrics.cuped_correlation === null || payload.metrics.cuped_correlation === undefined
      ? ""
      : Number(payload.metrics.cuped_correlation);

  return {
    ...payload,
    additional_context: additionalContext,
    setup: {
      ...payload.setup,
      traffic_split: Array.isArray(payload.setup.traffic_split)
        ? payload.setup.traffic_split.join(",")
        : String(payload.setup.traffic_split ?? "")
    },
    metrics: {
      ...payload.metrics,
      std_dev:
        payload.metrics.std_dev === "" || payload.metrics.std_dev === null || payload.metrics.std_dev === undefined
          ? ""
          : Number(payload.metrics.std_dev),
      exposure_per_user:
        payload.metrics.exposure_per_user === "" ||
        payload.metrics.exposure_per_user === null ||
        payload.metrics.exposure_per_user === undefined
          ? ""
          : Number(payload.metrics.exposure_per_user),
      cuped_pre_experiment_std: cupedPreExperimentStd,
      cuped_correlation: cupedCorrelation,
      cuped_enabled: cupedPreExperimentStd !== "" || cupedCorrelation !== "",
      planned_test: payload.metrics.planned_test ?? "z_test",
      equivalence_margin_pct:
        payload.metrics.equivalence_margin_pct === "" ||
        payload.metrics.equivalence_margin_pct === null ||
        payload.metrics.equivalence_margin_pct === undefined
          ? ""
          : Number(payload.metrics.equivalence_margin_pct),
      secondary_metrics: parseMetricList(payload.metrics.secondary_metrics).join(", "),
      guardrail_metrics: Array.isArray(payload.metrics.guardrail_metrics)
        ? payload.metrics.guardrail_metrics.map((guardrail) => {
            if (typeof guardrail === "string") {
              return {
                name: guardrail,
                metric_type: "binary",
                direction: "increase_is_bad",
                non_inferiority_margin_pct: ""
              };
            }

            const direction = guardrail.direction ?? "increase_is_bad";
            const non_inferiority_margin_pct =
              guardrail.non_inferiority_margin_pct === "" ||
              guardrail.non_inferiority_margin_pct === null ||
              guardrail.non_inferiority_margin_pct === undefined
                ? ""
                : Number(guardrail.non_inferiority_margin_pct);
            return guardrail.metric_type === "binary"
              ? {
                  name: guardrail.name,
                  metric_type: "binary",
                  baseline_rate:
                    guardrail.baseline_rate === "" || guardrail.baseline_rate === null || guardrail.baseline_rate === undefined
                      ? ""
                      : Number(guardrail.baseline_rate),
                  direction,
                  non_inferiority_margin_pct
                }
              : {
                  name: guardrail.name,
                  metric_type: "continuous",
                  baseline_mean:
                    guardrail.baseline_mean === "" || guardrail.baseline_mean === null || guardrail.baseline_mean === undefined
                      ? ""
                      : Number(guardrail.baseline_mean),
                  std_dev:
                    guardrail.std_dev === "" || guardrail.std_dev === null || guardrail.std_dev === undefined
                      ? ""
                      : Number(guardrail.std_dev),
                  direction,
                  non_inferiority_margin_pct
                };
          })
        : []
    }
  };
}
