// This file is auto-generated from FastAPI OpenAPI components.
// Do not edit manually. Run `python scripts/generate_frontend_api_types.py`.

export type AdditionalContext_Input = {
  llm_context?: string;
  observed_results?: SavedObservedResults_Input | null;
};

export type AdditionalContext_Output = {
  llm_context?: string;
  observed_results?: SavedObservedResults_Output | null;
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

export type AuditLogEntry = {
  id: number;
  ts: string;
  action: string;
  project_id?: string | null;
  project_name?: string | null;
  actor?: string | null;
  request_id?: string | null;
  payload_diff?: { [key: string]: unknown[]; } | null;
  ip_address?: string | null;
};

export type AuditLogResponse = {
  entries: AuditLogEntry[];
  total?: number;
};

export type CalculationRequest = {
  metric_type: "binary" | "continuous";
  baseline_value: number;
  std_dev?: number | null;
  cuped_pre_experiment_std?: number | null;
  cuped_correlation?: number | null;
  mde_pct: number;
  alpha: number;
  power: number;
  expected_daily_traffic: number;
  audience_share_in_test: number;
  traffic_split: number[];
  variants_count: number;
  actual_counts?: number[] | null;
  seasonality_present?: boolean | null;
  active_campaigns_present?: boolean | null;
  long_test_possible?: boolean | null;
  n_looks?: number;
  analysis_mode?: "frequentist" | "bayesian";
  desired_precision?: number | null;
  credibility?: number;
};

export type CalculationResponse = {
  calculation_summary: CalculationSummaryResponse;
  results: CalculationResultsResponse;
  assumptions: string[];
  warnings: WarningResponse[];
  bonferroni_note?: string | null;
  bayesian_sample_size_per_variant?: number | null;
  bayesian_credibility?: number | null;
  bayesian_note?: string | null;
  sequential_boundaries?: { [key: string]: unknown; }[] | null;
  sequential_inflation_factor?: number | null;
  sequential_adjusted_sample_size?: number | null;
  cuped_std?: number | null;
  cuped_sample_size_per_variant?: number | null;
  cuped_variance_reduction_pct?: number | null;
  cuped_duration_days?: number | null;
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
  n_looks?: number;
  analysis_mode?: "frequentist" | "bayesian";
  desired_precision?: number | null;
  credibility?: number;
};

export type DiagnosticsAuthSummary = {
  enabled: boolean;
  mode: string;
  write_enabled: boolean;
  readonly_enabled: boolean;
  accepted_headers: string[];
  read_only_methods: string[];
};

export type DiagnosticsFrontendSummary = {
  serve_frontend_dist: boolean;
  dist_path: string;
  dist_exists: boolean;
};

export type DiagnosticsGuardsSummary = {
  security_headers_enabled: boolean;
  rate_limit_enabled: boolean;
  rate_limit_requests: number;
  rate_limit_window_seconds: number;
  auth_failure_limit: number;
  auth_failure_window_seconds: number;
  max_request_body_bytes: number;
  max_workspace_body_bytes: number;
};

export type DiagnosticsLlmSummary = {
  provider: string;
  base_url: string;
  timeout_seconds: number;
  max_attempts: number;
  initial_backoff_seconds: number;
  backoff_multiplier: number;
};

export type DiagnosticsLoggingSummary = {
  level: string;
  format: string;
};

export type DiagnosticsResponse = {
  status: string;
  generated_at: string;
  started_at: string;
  uptime_seconds: number;
  environment: string;
  app_version: string;
  request_timing_headers_enabled: boolean;
  storage: DiagnosticsStorageSummary;
  frontend: DiagnosticsFrontendSummary;
  llm: DiagnosticsLlmSummary;
  logging: DiagnosticsLoggingSummary;
  auth: DiagnosticsAuthSummary;
  guards: DiagnosticsGuardsSummary;
  runtime: DiagnosticsRuntimeSummary;
};

export type DiagnosticsRuntimeSummary = {
  total_requests: number;
  success_responses: number;
  client_error_responses: number;
  server_error_responses: number;
  auth_rejections: number;
  rate_limited_responses?: number;
  request_body_rejections?: number;
  last_request_at?: string | null;
  last_error_at?: string | null;
  last_error_code?: string | null;
};

export type DiagnosticsStorageSummary = {
  db_path: string;
  db_parent_path: string;
  db_exists: boolean;
  db_size_bytes: number;
  disk_free_bytes: number;
  schema_version: number;
  sqlite_user_version: number;
  busy_timeout_ms: number;
  journal_mode: string;
  synchronous: string;
  write_probe_ok: boolean;
  write_probe_detail: string;
  projects_total: number;
  archived_projects_total: number;
  analysis_runs_total: number;
  export_events_total: number;
  project_revisions_total: number;
  workspace_bundle_schema_version: number;
  workspace_signature_enabled: boolean;
  latest_project_updated_at?: string | null;
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

export type ExperimentInput_Input = {
  project: ProjectContext;
  hypothesis: HypothesisContext;
  setup: ExperimentSetup;
  metrics: MetricsConfig;
  constraints: ConstraintsConfig;
  additional_context?: AdditionalContext_Input;
};

export type ExperimentInput_Output = {
  project: ProjectContext;
  hypothesis: HypothesisContext;
  setup: ExperimentSetup;
  metrics: MetricsConfig;
  constraints: ConstraintsConfig;
  additional_context?: AdditionalContext_Output;
};

export type ExperimentReport_Input = {
  executive_summary: string;
  calculations: CalculationsSection;
  experiment_design: ExperimentDesignSection;
  metrics_plan: MetricsPlanSection;
  guardrail_metrics?: GuardrailMetricReport[];
  risks: RisksSection;
  recommendations: RecommendationsSection;
  open_questions: string[];
};

export type ExperimentReport_Output = {
  executive_summary: string;
  calculations: CalculationsSection;
  experiment_design: ExperimentDesignSection;
  metrics_plan: MetricsPlanSection;
  guardrail_metrics?: GuardrailMetricReport[];
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
  format: "markdown" | "html" | "pdf";
  created_at: string;
};

export type ExportResponse = {
  content: string;
};

export type GuardrailMetricInput = {
  name: string;
  metric_type: "binary" | "continuous";
  baseline_rate?: number | null;
  baseline_mean?: number | null;
  std_dev?: number | null;
};

export type GuardrailMetricReport = {
  name: string;
  metric_type: string;
  baseline: number;
  detectable_mde_pp?: number | null;
  detectable_mde_absolute?: number | null;
  note: string;
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
  cuped_pre_experiment_std?: number | null;
  cuped_correlation?: number | null;
  secondary_metrics?: string[];
  guardrail_metrics?: GuardrailMetricInput[];
};

export type MetricsPlanSection = {
  primary: string[];
  secondary: string[];
  guardrail: string[];
  diagnostic: string[];
};

export type ObservedResultsBinary = {
  control_conversions: number;
  control_users: number;
  treatment_conversions: number;
  treatment_users: number;
  alpha?: number;
};

export type ObservedResultsContinuous = {
  control_mean: number;
  control_std: number;
  control_n: number;
  treatment_mean: number;
  treatment_std: number;
  treatment_n: number;
  alpha?: number;
};

export type ProjectArchiveResponse = {
  id: string;
  archived: boolean;
  archived_at?: string | null;
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
  executive_summary: string;
  warning_severity: string;
  recommendation_highlights: string[];
};

export type ProjectComparisonResponse = {
  base_project: ProjectComparisonItem;
  candidate_project: ProjectComparisonItem;
  deltas: ProjectComparisonDelta;
  shared_warning_codes: string[];
  base_only_warning_codes: string[];
  candidate_only_warning_codes: string[];
  shared_assumptions: string[];
  base_only_assumptions: string[];
  candidate_only_assumptions: string[];
  shared_risk_highlights: string[];
  base_only_risk_highlights: string[];
  candidate_only_risk_highlights: string[];
  metric_alignment_note: string;
  highlights: string[];
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
  format: "markdown" | "html" | "pdf";
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
  hypothesis?: string | null;
  metric_type?: ("binary" | "continuous") | null;
  duration_days?: number | null;
  payload_schema_version: number;
  archived_at?: string | null;
  is_archived?: boolean;
  revision_count?: number;
  last_revision_at?: string | null;
  last_analysis_at?: string | null;
  last_analysis_run_id?: string | null;
  last_exported_at?: string | null;
  has_analysis_snapshot?: boolean;
  created_at: string;
  updated_at: string;
};

export type ProjectListResponse = {
  projects: ProjectListItem[];
  total?: number;
  offset?: number;
  limit?: number;
  has_more?: boolean;
};

export type ProjectRecord = {
  id: string;
  project_name: string;
  payload_schema_version: number;
  archived_at?: string | null;
  is_archived?: boolean;
  revision_count?: number;
  last_revision_at?: string | null;
  last_analysis_at?: string | null;
  last_analysis_run_id?: string | null;
  last_exported_at?: string | null;
  has_analysis_snapshot?: boolean;
  created_at: string;
  updated_at: string;
  payload: ExperimentInput_Output;
};

export type ProjectRevisionHistoryResponse = {
  project_id: string;
  total: number;
  limit: number;
  offset: number;
  revisions: ProjectRevisionRecord[];
};

export type ProjectRevisionRecord = {
  id: string;
  project_id: string;
  source: "create" | "update" | "workspace_import";
  created_at: string;
  payload: ExperimentInput_Output;
};

export type ReadinessCheck = {
  name: string;
  ok: boolean;
  detail: string;
};

export type ReadinessResponse = {
  status: string;
  generated_at: string;
  checks: ReadinessCheck[];
};

export type RecommendationsSection = {
  before_launch: string[];
  during_test: string[];
  after_test: string[];
};

export type ResultsRequest = {
  metric_type: "binary" | "continuous";
  binary?: ObservedResultsBinary | null;
  continuous?: ObservedResultsContinuous | null;
};

export type ResultsResponse = {
  metric_type: string;
  observed_effect: number;
  observed_effect_relative: number;
  control_rate?: number | null;
  treatment_rate?: number | null;
  ci_lower: number;
  ci_upper: number;
  ci_level: number;
  p_value: number;
  test_statistic: number;
  is_significant: boolean;
  power_achieved: number;
  verdict: string;
  interpretation: string;
};

export type RisksSection = {
  statistical: string[];
  product: string[];
  technical: string[];
  operational: string[];
};

export type SavedObservedResults_Input = {
  request: ResultsRequest;
  analysis: ResultsResponse;
  saved_at?: string | null;
};

export type SavedObservedResults_Output = {
  request: ResultsRequest;
  analysis: ResultsResponse;
  saved_at?: string | null;
};

export type SensitivityCell = {
  mde: number;
  power: number;
  sample_size_per_variant: number;
  duration_days: number;
};

export type SensitivityRequest = {
  metric_type: "binary" | "continuous";
  baseline_rate?: number | null;
  baseline_mean?: number | null;
  std_dev?: number | null;
  variants?: number;
  alpha?: number;
  daily_traffic?: number;
  audience_share?: number;
  traffic_split?: number[] | null;
  mde_values?: number[];
  power_values?: number[];
};

export type SensitivityResponse = {
  cells: SensitivityCell[];
  current_mde?: number | null;
  current_power?: number | null;
};

export type SrmCheckRequest = {
  observed_counts: number[];
  expected_fractions: number[];
};

export type SrmCheckResponse = {
  chi_square: number;
  p_value: number;
  is_srm: boolean;
  verdict: string;
  observed_counts: number[];
  expected_counts: number[];
};

export type StandaloneExportRequest = {
  project_name: string;
  hypothesis?: string | null;
  calculation: { [key: string]: unknown; };
  design: { [key: string]: unknown; };
  ai_advice?: { [key: string]: unknown; } | null;
  sensitivity?: { [key: string]: unknown; } | null;
  results?: { [key: string]: unknown; } | null;
};

export type TemplateCreateRequest = {
  name: string;
  category?: string;
  description: string;
  tags?: string[];
  payload: ExperimentInput_Input;
};

export type TemplateDeleteResponse = {
  id: string;
  deleted: boolean;
};

export type TemplateListResponse = {
  templates: TemplateRecord[];
  total?: number;
};

export type TemplateRecord = {
  id: string;
  name: string;
  category: string;
  description: string;
  built_in: boolean;
  payload: ExperimentInput_Output;
  tags?: string[];
  usage_count?: number;
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

export type WorkspaceAnalysisRunRecord_Input = {
  id: string;
  project_id: string;
  created_at: string;
  analysis: AnalysisResponse_Input;
};

export type WorkspaceAnalysisRunRecord_Output = {
  id: string;
  project_id: string;
  created_at: string;
  analysis: AnalysisResponse_Output;
};

export type WorkspaceBundle_Input = {
  schema_version?: number;
  generated_at: string;
  projects: WorkspaceProjectRecord_Input[];
  analysis_runs: WorkspaceAnalysisRunRecord_Input[];
  export_events: WorkspaceExportEventRecord[];
  project_revisions?: WorkspaceProjectRevisionRecord_Input[];
  integrity?: WorkspaceIntegrity | null;
};

export type WorkspaceBundle_Output = {
  schema_version?: number;
  generated_at: string;
  projects: WorkspaceProjectRecord_Output[];
  analysis_runs: WorkspaceAnalysisRunRecord_Output[];
  export_events: WorkspaceExportEventRecord[];
  project_revisions?: WorkspaceProjectRevisionRecord_Output[];
  integrity?: WorkspaceIntegrity | null;
};

export type WorkspaceExportEventRecord = {
  id: string;
  project_id: string;
  analysis_run_id?: string | null;
  format: "markdown" | "html" | "pdf";
  created_at: string;
};

export type WorkspaceImportResponse = {
  status: string;
  imported_projects: number;
  imported_analysis_runs: number;
  imported_export_events: number;
  imported_project_revisions?: number;
};

export type WorkspaceIntegrity = {
  counts: WorkspaceIntegrityCounts;
  checksum_sha256: string;
  signature_hmac_sha256?: string | null;
};

export type WorkspaceIntegrityCounts = {
  projects: number;
  analysis_runs: number;
  export_events: number;
  project_revisions: number;
};

export type WorkspaceProjectRecord_Input = {
  id: string;
  project_name: string;
  payload_schema_version: number;
  archived_at?: string | null;
  last_analysis_at?: string | null;
  last_analysis_run_id?: string | null;
  last_exported_at?: string | null;
  created_at: string;
  updated_at: string;
  payload: ExperimentInput_Input;
};

export type WorkspaceProjectRecord_Output = {
  id: string;
  project_name: string;
  payload_schema_version: number;
  archived_at?: string | null;
  last_analysis_at?: string | null;
  last_analysis_run_id?: string | null;
  last_exported_at?: string | null;
  created_at: string;
  updated_at: string;
  payload: ExperimentInput_Output;
};

export type WorkspaceProjectRevisionRecord_Input = {
  id: string;
  project_id: string;
  source: "create" | "update" | "workspace_import";
  created_at: string;
  payload: ExperimentInput_Input;
};

export type WorkspaceProjectRevisionRecord_Output = {
  id: string;
  project_id: string;
  source: "create" | "update" | "workspace_import";
  created_at: string;
  payload: ExperimentInput_Output;
};

export type WorkspaceValidationResponse = {
  status: string;
  schema_version: number;
  counts: WorkspaceIntegrityCounts;
  checksum_sha256: string;
  signature_verified?: boolean;
};
