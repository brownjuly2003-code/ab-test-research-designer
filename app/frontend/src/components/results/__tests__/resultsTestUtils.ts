import type {
  AnalysisResponsePayload,
  ProjectComparison,
  ProjectHistory,
  SavedProject
} from "../../../lib/experiment";
import { useAnalysisStore } from "../../../stores/analysisStore";
import { useProjectStore } from "../../../stores/projectStore";

const initialAnalysisState = useAnalysisStore.getState();
const initialProjectState = useProjectStore.getState();

export const defaultSensitivityData = {
  cells: [
    {
      mde: 1,
      power: 0.8,
      sample_size_per_variant: 120,
      total_sample_size: 240,
      duration_days: 9
    },
    {
      mde: 2,
      power: 0.8,
      sample_size_per_variant: 80,
      total_sample_size: 160,
      duration_days: 6
    }
  ]
};

export function resetResultsStores() {
  useAnalysisStore.setState(initialAnalysisState, true);
  useProjectStore.setState(initialProjectState, true);
}

export function buildAnalysisResult(options: {
  adviceAvailable?: boolean;
  metricType?: "binary" | "continuous";
} = {}): AnalysisResponsePayload {
  const metricType = options.metricType ?? "binary";
  const isContinuous = metricType === "continuous";

  return {
    calculations: {
      calculation_summary: {
        metric_type: metricType,
        baseline_value: isContinuous ? 45 : 0.042,
        mde_pct: 5,
        mde_absolute: isContinuous ? 2 : 0.0021,
        alpha: 0.05,
        power: 0.8
      },
      results: {
        sample_size_per_variant: 100,
        total_sample_size: 300,
        effective_daily_traffic: 5000,
        estimated_duration_days: 12
      },
      assumptions: [],
      warnings: [
        {
          code: "SEASONALITY_PRESENT",
          severity: "medium",
          message: "Seasonality may affect the baseline.",
          source: "heuristic"
        }
      ],
      bonferroni_note: "Bonferroni adjustment applied across guardrails.",
      cuped_std: isContinuous ? 10.3923 : null,
      cuped_sample_size_per_variant: isContinuous ? 75 : null,
      cuped_variance_reduction_pct: isContinuous ? 25 : null,
      cuped_duration_days: isContinuous ? 8 : null,
      bayesian_sample_size_per_variant: isContinuous ? 10800 : null,
      bayesian_credibility: isContinuous ? 0.95 : null,
      bayesian_note: isContinuous
        ? "Bayesian estimate: N=10,800 per variant gives a 95% credible interval."
        : null,
      sequential_boundaries: [
        {
          look: 1,
          info_fraction: 0.5,
          cumulative_alpha_spent: 0.005,
          z_boundary: 2.8,
          is_final: false
        },
        {
          look: 2,
          info_fraction: 1,
          cumulative_alpha_spent: 0.05,
          z_boundary: 1.96,
          is_final: true
        }
      ],
      sequential_inflation_factor: 1.12,
      sequential_adjusted_sample_size: 112
    },
    report: {
      executive_summary: "Deterministic summary",
      calculations: {
        sample_size_per_variant: 100,
        total_sample_size: 300,
        estimated_duration_days: 12,
        assumptions: ["Baseline is stable", "Traffic split will hold"]
      },
      experiment_design: {
        variants: [
          { name: "Control", description: "Current checkout" },
          { name: "Treatment", description: "New checkout" }
        ],
        randomization_unit: "user",
        traffic_split: [50, 50],
        target_audience: "new users on web",
        inclusion_criteria: "new users only",
        exclusion_criteria: "internal staff",
        recommended_duration_days: 12,
        stopping_conditions: ["planned duration reached", "guardrail breach"]
      },
      metrics_plan: {
        primary: ["purchase_conversion"],
        secondary: ["add_to_cart_rate"],
        guardrail: ["payment_error_rate"],
        diagnostic: ["assignment_rate"]
      },
      guardrail_metrics: [
        {
          name: "Payment error rate",
          metric_type: "binary",
          baseline: 2.4,
          detectable_mde_pp: 0.321,
          note: "With N=100 per variant, can detect >= 0.32 pp change."
        }
      ],
      risks: {
        statistical: ["Monitor peeking risk."],
        product: ["Behavior may differ on mobile."],
        technical: ["Legacy event logging requires validation."],
        operational: ["Track assignment health daily."]
      },
      recommendations: {
        before_launch: ["Verify tracking"],
        during_test: ["Watch SRM"],
        after_test: ["Segment the result"]
      },
      open_questions: ["Will mobile respond differently?"]
    },
    advice: {
      available: options.adviceAvailable ?? true,
      provider: "local_orchestrator",
      model: options.adviceAvailable ?? true ? "offline-guidance" : "offline",
      advice: options.adviceAvailable ?? true
        ? {
            brief_assessment: "The experiment is feasible with careful monitoring.",
            key_risks: ["Tracking quality may skew results."],
            design_improvements: ["Validate assignment logging before launch."],
            metric_recommendations: ["Track checkout step completion by segment."],
            interpretation_pitfalls: ["Do not over-read the first 48 hours."],
            additional_checks: ["Verify exposure balance by traffic source."]
          }
        : null,
      raw_text: null,
      error: options.adviceAvailable ?? true ? null : "offline",
      error_code: options.adviceAvailable ?? true ? null : "request_error"
    }
  };
}

export function buildActiveProject(projectId = "p-1"): SavedProject {
  return {
    id: projectId,
    project_name: "Stored checkout test",
    payload_schema_version: 1,
    created_at: "2026-03-07T10:00:00Z",
    updated_at: "2026-03-07T12:40:00Z",
    archived_at: null,
    is_archived: false,
    revision_count: 2,
    last_revision_at: "2026-03-07T12:10:00Z",
    last_analysis_at: "2026-03-07T12:30:00Z",
    last_analysis_run_id: "run-1",
    last_exported_at: "2026-03-07T12:45:00Z",
    has_analysis_snapshot: true
  };
}

export function buildProjectHistory(
  analysis: AnalysisResponsePayload,
  projectId = "p-1"
): ProjectHistory {
  return {
    project_id: projectId,
    analysis_total: 1,
    analysis_limit: 3,
    analysis_offset: 0,
    export_total: 1,
    export_limit: 3,
    export_offset: 0,
    analysis_runs: [
      {
        id: "run-1",
        project_id: projectId,
        created_at: "2026-03-07T12:30:00Z",
        summary: {
          metric_type: analysis.calculations.calculation_summary.metric_type,
          sample_size_per_variant: 100,
          total_sample_size: 300,
          estimated_duration_days: 12,
          warnings_count: 1,
          advice_available: analysis.advice.available
        },
        analysis
      }
    ],
    export_events: [
      {
        id: "export-1",
        project_id: projectId,
        analysis_run_id: "run-1",
        format: "markdown",
        created_at: "2026-03-07T12:45:00Z"
      }
    ]
  };
}

export function buildProjectComparison(): ProjectComparison {
  return {
    base_project: {
      id: "p-1",
      project_name: "Stored checkout test",
      updated_at: "2026-03-07T10:00:00Z",
      analysis_created_at: "2026-03-07T12:30:00Z",
      last_analysis_at: "2026-03-07T12:30:00Z",
      analysis_run_id: "run-1",
      metric_type: "binary",
      primary_metric: "purchase_conversion",
      sample_size_per_variant: 100,
      total_sample_size: 300,
      estimated_duration_days: 12,
      warnings_count: 1,
      warning_codes: ["SEASONALITY_PRESENT"],
      risk_highlights: ["tracking quality"],
      assumptions: ["Baseline is stable"],
      advice_available: false,
      executive_summary: "Stored checkout summary",
      warning_severity: "medium",
      recommendation_highlights: ["Verify tracking", "Watch SRM"]
    },
    candidate_project: {
      id: "p-2",
      project_name: "Pricing challenger",
      updated_at: "2026-03-07T11:00:00Z",
      analysis_created_at: "2026-03-07T13:00:00Z",
      last_analysis_at: "2026-03-07T13:00:00Z",
      analysis_run_id: "run-2",
      metric_type: "binary",
      primary_metric: "purchase_conversion",
      sample_size_per_variant: 140,
      total_sample_size: 360,
      estimated_duration_days: 15,
      warnings_count: 2,
      warning_codes: ["LONG_DURATION", "LOW_TRAFFIC"],
      risk_highlights: ["tracking quality"],
      assumptions: ["Baseline is stable"],
      advice_available: false,
      executive_summary: "Pricing challenger summary",
      warning_severity: "high",
      recommendation_highlights: ["Validate traffic quality", "Watch SRM"]
    },
    deltas: {
      sample_size_per_variant: 40,
      total_sample_size: 60,
      estimated_duration_days: 3,
      warnings_count: 1
    },
    shared_warning_codes: [],
    base_only_warning_codes: ["SEASONALITY_PRESENT"],
    candidate_only_warning_codes: ["LONG_DURATION", "LOW_TRAFFIC"],
    shared_assumptions: ["Baseline is stable"],
    base_only_assumptions: [],
    candidate_only_assumptions: [],
    shared_risk_highlights: ["tracking quality"],
    base_only_risk_highlights: [],
    candidate_only_risk_highlights: [],
    metric_alignment_note: "Both snapshots evaluate the same primary metric and metric family.",
    highlights: [
      "Pricing challenger changes total sample size by +60 and estimated duration by +3 days versus Stored checkout test.",
      "Both snapshots evaluate the same primary metric and metric family."
    ],
    summary: "Pricing challenger needs larger total sample size and a longer test window than Stored checkout test."
  };
}

export function seedResultsStores(options: {
  analysis?: AnalysisResponsePayload | null;
  activeProject?: SavedProject | null;
  projectHistory?: ProjectHistory | null;
  selectedHistoryRunId?: string | null;
  projectComparison?: ProjectComparison | null;
  canMutateBackend?: boolean;
  backendMutationMessage?: string;
} = {}) {
  const analysis = options.analysis ?? buildAnalysisResult();
  const projectHistory = options.projectHistory ?? buildProjectHistory(analysis);
  const activeProject = options.activeProject ?? buildActiveProject(projectHistory.project_id);
  const selectedHistoryRun =
    options.selectedHistoryRunId
      ? projectHistory.analysis_runs.find((run) => run.id === options.selectedHistoryRunId) ?? null
      : null;

  useAnalysisStore.setState({
    ...useAnalysisStore.getState(),
    analysisResult: analysis,
    results: {
      calculations: analysis.calculations,
      report: analysis.report,
      advice: analysis.advice
    },
    isAnalyzing: false,
    loading: false,
    analysisError: "",
    error: "",
    statusMessage: "",
    resultsProjectId: activeProject?.id ?? null,
    resultsAnalysisRunId: selectedHistoryRun?.id ?? activeProject?.last_analysis_run_id ?? null,
    validationErrors: []
  });

  useProjectStore.setState({
    ...useProjectStore.getState(),
    activeProjectId: activeProject?.id ?? null,
    savedProjects: activeProject ? [activeProject] : [],
    projectHistory,
    selectedHistoryRunId: selectedHistoryRun?.id ?? null,
    projectComparison: options.projectComparison ?? null,
    projectError: "",
    loadingProjectHistory: false,
    activeProject,
    selectedHistoryRun,
    canMutateBackend: options.canMutateBackend ?? true,
    backendMutationMessage: options.backendMutationMessage ?? ""
  });
}
