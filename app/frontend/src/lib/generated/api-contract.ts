// This file is auto-generated from FastAPI OpenAPI components.
// Do not edit manually. Run `python scripts/generate_frontend_api_types.py`.

export type AdditionalContext = {
  llm_context?: string;
};

export type AdvicePayload = {
  brief_assessment: string;
  key_risks: string[];
  design_improvements: string[];
  metric_recommendations: string[];
  interpretation_pitfalls: string[];
  additional_checks: string[];
};

export type AnalysisResponse_Input = {
  calculations: CalculationResponse;
  report: ExperimentReport_Input;
  advice: LlmAdviceResponse;
};

export type AnalysisResponse_Output = {
  calculations: CalculationResponse;
  report: ExperimentReport_Output;
  advice: LlmAdviceResponse;
};

export type AnalysisRunRecord = {
  id: string;
  project_id: string;
  created_at: string;
  summary: AnalysisRunSummary;
  analysis: AnalysisResponse_Output;
};

export type AnalysisRunSummary = {
  metric_type?: string | null;
  sample_size_per_variant?: number | null;
  total_sample_size?: number | null;
  estimated_duration_days?: number | null;
  warnings_count?: number;
  advice_available?: boolean;
};

export type CalculationRequest = {
  metric_type: "binary" | "continuous";
  baseline_value: number;
  std_dev?: number | null;
  mde_pct: number;
  alpha: number;
  power: number;
  expected_daily_traffic: number;
  audience_share_in_test: number;
  traffic_split: number[];
  variants_count: number;
  seasonality_present?: boolean | null;
  active_campaigns_present?: boolean | null;
  long_test_possible?: boolean | null;
};

export type CalculationResponse = {
  calculation_summary: CalculationSummaryResponse;
  results: CalculationResultsResponse;
  assumptions: string[];
  warnings: WarningResponse[];
  bonferroni_note?: string | null;
};

export type CalculationResultsResponse = {
  sample_size_per_variant: number;
  total_sample_size: number;
  effective_daily_traffic: number;
  estimated_duration_days: number;
};

export type CalculationSummaryResponse = {
  metric_type: string;
  baseline_value: number;
  mde_pct: number;
  mde_absolute: number;
  alpha: number;
  power: number;
};

export type CalculationsSection = {
  sample_size_per_variant: number;
  total_sample_size: number;
  estimated_duration_days: number;
  assumptions: string[];
};

export type ConstraintsConfig = {
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

export type ExperimentDesignSection = {
  variants: VariantDefinition[];
  randomization_unit: string;
  traffic_split: number[];
  target_audience: string;
  inclusion_criteria: string;
  exclusion_criteria: string;
  recommended_duration_days: number;
  stopping_conditions: string[];
};

export type ExperimentInput = {
  project: ProjectContext;
  hypothesis: HypothesisContext;
  setup: ExperimentSetup;
  metrics: MetricsConfig;
  constraints: ConstraintsConfig;
  additional_context?: AdditionalContext;
};

export type ExperimentReport_Input = {
  executive_summary: string;
  calculations: CalculationsSection;
  experiment_design: ExperimentDesignSection;
  metrics_plan: MetricsPlanSection;
  risks: RisksSection;
  recommendations: RecommendationsSection;
  open_questions: string[];
};

export type ExperimentReport_Output = {
  executive_summary: string;
  calculations: CalculationsSection;
  experiment_design: ExperimentDesignSection;
  metrics_plan: MetricsPlanSection;
  risks: RisksSection;
  recommendations: RecommendationsSection;
  open_questions: string[];
};

export type ExperimentSetup = {
  experiment_type: string;
  randomization_unit: string;
  traffic_split: number[];
  expected_daily_traffic: number;
  audience_share_in_test: number;
  variants_count: number;
  inclusion_criteria: string;
  exclusion_criteria: string;
};

export type ExportEventRecord = {
  id: string;
  project_id: string;
  analysis_run_id?: string | null;
  format: "markdown" | "html";
  created_at: string;
};

export type ExportResponse = {
  content: string;
};

export type HTTPValidationError = {
  detail?: ValidationError[];
};

export type HealthResponse = {
  status: string;
  service: string;
  version: string;
  environment: string;
};

export type HypothesisContext = {
  change_description: string;
  target_audience: string;
  business_problem: string;
  hypothesis_statement: string;
  what_to_validate: string;
  desired_result: string;
};

export type LlmAdviceRequest = {
  project_context: { [key: string]: unknown; };
  hypothesis?: { [key: string]: unknown; } | null;
  setup?: { [key: string]: unknown; } | null;
  metrics?: { [key: string]: unknown; } | null;
  constraints?: { [key: string]: unknown; } | null;
  additional_context?: { [key: string]: unknown; } | null;
  calculation_results?: { [key: string]: unknown; } | null;
  warnings?: { [key: string]: unknown; }[] | null;
  [key: string]: unknown;
};

export type LlmAdviceResponse = {
  available: boolean;
  provider: string;
  model: string;
  advice: AdvicePayload | null;
  raw_text: string | null;
  error: string | null;
  error_code?: string | null;
};

export type MetricsConfig = {
  primary_metric_name: string;
  metric_type: "binary" | "continuous";
  baseline_value: number;
  expected_uplift_pct?: number | null;
  mde_pct: number;
  alpha: number;
  power: number;
  std_dev?: number | null;
  secondary_metrics?: string[];
  guardrail_metrics?: string[];
};

export type MetricsPlanSection = {
  primary: string[];
  secondary: string[];
  guardrail: string[];
  diagnostic: string[];
};

export type ProjectComparisonDelta = {
  sample_size_per_variant: number;
  total_sample_size: number;
  estimated_duration_days: number;
  warnings_count: number;
};

export type ProjectComparisonItem = {
  id: string;
  project_name: string;
  updated_at: string;
  analysis_created_at: string;
  last_analysis_at?: string | null;
  analysis_run_id: string;
  metric_type: string;
  primary_metric: string;
  sample_size_per_variant: number;
  total_sample_size: number;
  estimated_duration_days: number;
  warnings_count: number;
  warning_codes: string[];
  risk_highlights: string[];
  assumptions: string[];
  advice_available: boolean;
};

export type ProjectComparisonResponse = {
  base_project: ProjectComparisonItem;
  candidate_project: ProjectComparisonItem;
  deltas: ProjectComparisonDelta;
  shared_warning_codes: string[];
  base_only_warning_codes: string[];
  candidate_only_warning_codes: string[];
  summary: string;
};

export type ProjectContext = {
  project_name: string;
  domain: string;
  product_type: string;
  platform: string;
  market: string;
  project_description: string;
};

export type ProjectDeleteResponse = {
  id: string;
  deleted: boolean;
};

export type ProjectExportMarkRequest = {
  format: "markdown" | "html";
  analysis_run_id?: string | null;
};

export type ProjectHistoryResponse = {
  project_id: string;
  analysis_total: number;
  analysis_limit: number;
  analysis_offset: number;
  export_total: number;
  export_limit: number;
  export_offset: number;
  analysis_runs: AnalysisRunRecord[];
  export_events: ExportEventRecord[];
};

export type ProjectListItem = {
  id: string;
  project_name: string;
  payload_schema_version: number;
  last_analysis_at?: string | null;
  last_analysis_run_id?: string | null;
  last_exported_at?: string | null;
  has_analysis_snapshot?: boolean;
  created_at: string;
  updated_at: string;
};

export type ProjectListResponse = {
  projects: ProjectListItem[];
};

export type ProjectRecord = {
  id: string;
  project_name: string;
  payload_schema_version: number;
  last_analysis_at?: string | null;
  last_analysis_run_id?: string | null;
  last_exported_at?: string | null;
  has_analysis_snapshot?: boolean;
  created_at: string;
  updated_at: string;
  payload: ExperimentInput;
};

export type RecommendationsSection = {
  before_launch: string[];
  during_test: string[];
  after_test: string[];
};

export type RisksSection = {
  statistical: string[];
  product: string[];
  technical: string[];
  operational: string[];
};

export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
  input?: unknown;
  ctx?: {};
};

export type VariantDefinition = {
  name: string;
  description: string;
};

export type WarningResponse = {
  code: string;
  severity: string;
  message: string;
  source: string;
};
