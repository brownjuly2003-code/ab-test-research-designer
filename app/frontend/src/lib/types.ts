import type {
  AnalysisResponse_Output as ApiAnalysisResponse,
  AnalysisRunRecord as ApiAnalysisRunRecord,
  CalculationRequest as ApiCalculationRequest,
  CalculationResponse as ApiCalculationResponse,
  DiagnosticsResponse as ApiDiagnosticsResponseContract,
  ExperimentInput_Input as ApiExperimentInputInput,
  ExperimentInput_Output as ApiExperimentInputOutput,
  ExperimentReport_Output as ApiExperimentReport,
  ExportEventRecord as ApiExportEventRecord,
  HealthResponse as ApiHealthResponseContract,
  LlmAdviceResponse as ApiLlmAdviceResponse,
  ProjectComparisonResponse as ApiProjectComparisonResponse,
  ProjectHistoryResponse as ApiProjectHistoryResponse,
  ProjectListItem as ApiProjectListItem,
  ProjectRecord as ApiProjectRecord,
  ProjectRevisionHistoryResponse as ApiProjectRevisionHistoryResponse,
  ProjectRevisionRecord as ApiProjectRevisionRecord,
  WorkspaceBundle_Input as ApiWorkspaceBundleInput,
  WorkspaceBundle_Output as ApiWorkspaceBundleOutput,
  WorkspaceImportResponse as ApiWorkspaceImportResponse,
  WorkspaceValidationResponse as ApiWorkspaceValidationResponse
} from "./generated/api-contract";

export type ObservedResultsBinaryPayload = {
  control_conversions: number;
  control_users: number;
  treatment_conversions: number;
  treatment_users: number;
  alpha?: number;
};
export type ObservedResultsContinuousPayload = {
  control_mean: number;
  control_std: number;
  control_n: number;
  treatment_mean: number;
  treatment_std: number;
  treatment_n: number;
  alpha?: number;
};
export type ResultsRequestPayload = {
  metric_type: "binary" | "continuous";
  binary?: ObservedResultsBinaryPayload | null;
  continuous?: ObservedResultsContinuousPayload | null;
};
export type ResultsAnalysisResponse = {
  metric_type: "binary" | "continuous";
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
export type SavedObservedResults = {
  request: ResultsRequestPayload;
  analysis: ResultsAnalysisResponse;
  saved_at?: string | null;
};
export type AdditionalContextSection = NonNullable<ApiExperimentInputInput["additional_context"]> & {
  observed_results?: SavedObservedResults | null;
};
export type AnalysisMode = "frequentist" | "bayesian";
export type ConstraintsPayloadSection = ApiExperimentInputInput["constraints"] & {
  analysis_mode?: AnalysisMode;
  desired_precision?: number | null;
  credibility?: number | null;
};
export type ExperimentInputPayload = Omit<ApiExperimentInputInput, "additional_context" | "constraints"> & {
  constraints: ConstraintsPayloadSection;
  additional_context: AdditionalContextSection;
};
export type ExperimentInputRecordPayload = Omit<ApiExperimentInputOutput, "additional_context" | "constraints"> & {
  constraints: ConstraintsPayloadSection;
  additional_context: AdditionalContextSection;
};
export type HydratableExperimentInput =
  | ExperimentInputPayload
  | ExperimentInputRecordPayload
  | ApiExperimentInputOutput;
export type ProjectSection = ExperimentInputPayload["project"];
export type HypothesisSection = ExperimentInputPayload["hypothesis"];
export type SetupPayloadSection = ExperimentInputPayload["setup"];
export type MetricsPayloadSection = ExperimentInputPayload["metrics"];
export type ConstraintsSection = ExperimentInputPayload["constraints"];
export type MetricType = MetricsPayloadSection["metric_type"];
export type GuardrailMetricPayload = NonNullable<MetricsPayloadSection["guardrail_metrics"]>[number];
export type GuardrailMetricDraft = Omit<GuardrailMetricPayload, "baseline_rate" | "baseline_mean" | "std_dev"> & {
  baseline_rate?: number | "";
  baseline_mean?: number | "";
  std_dev?: number | "";
};
export type GuardrailMetricResult = NonNullable<ApiExperimentReport["guardrail_metrics"]>[number];

export type SetupDraftSection = Omit<SetupPayloadSection, "traffic_split"> & {
  traffic_split: string;
};

export type MetricsDraftSection = Omit<
  MetricsPayloadSection,
  "std_dev" | "cuped_pre_experiment_std" | "cuped_correlation" | "secondary_metrics" | "guardrail_metrics"
> & {
  std_dev: number | "";
  cuped_pre_experiment_std: number | "";
  cuped_correlation: number | "";
  cuped_enabled: boolean;
  secondary_metrics: string;
  guardrail_metrics: GuardrailMetricDraft[];
};

export type FullPayload = Omit<ExperimentInputPayload, "setup" | "metrics" | "additional_context"> & {
  setup: SetupDraftSection;
  metrics: MetricsDraftSection;
  additional_context: AdditionalContextSection;
};

export type LoadedPayload = Omit<HydratableExperimentInput, "setup" | "metrics" | "additional_context"> & {
  setup: Omit<SetupPayloadSection, "traffic_split"> & {
    traffic_split: string | number[];
  };
  metrics: Omit<
    MetricsDraftSection,
    "std_dev" | "cuped_pre_experiment_std" | "cuped_correlation" | "cuped_enabled" | "secondary_metrics" | "guardrail_metrics"
  > & {
    std_dev: number | "" | null;
    cuped_pre_experiment_std: number | "" | null;
    cuped_correlation: number | "" | null;
    cuped_enabled?: boolean;
    secondary_metrics: string | string[];
    guardrail_metrics: GuardrailMetricPayload[] | GuardrailMetricDraft[] | string[];
  };
  additional_context: AdditionalContextSection;
};

export type CalculationRequestPayload = ApiCalculationRequest & {
  analysis_mode?: AnalysisMode;
  desired_precision?: number | null;
  credibility?: number | null;
};

export type ApiErrorResponse = {
  detail?: string | unknown;
  error_code?: string;
  status_code?: number;
  request_id?: string;
};

export type WarningItem = ApiCalculationResponse["warnings"][number];
export type CalculationSummary = ApiCalculationResponse["calculation_summary"];
export type CalculationResponse = ApiCalculationResponse & {
  bayesian_sample_size_per_variant?: number | null;
  bayesian_credibility?: number | null;
  bayesian_note?: string | null;
};
export type ReportResponse = ApiExperimentReport;
export type AdvicePayload = NonNullable<ApiLlmAdviceResponse["advice"]>;
export type AdviceResponse = ApiLlmAdviceResponse;
export type ProjectActivityMeta = Pick<
  ApiProjectRecord,
  | "payload_schema_version"
  | "revision_count"
  | "last_revision_at"
  | "last_analysis_at"
  | "last_analysis_run_id"
  | "last_exported_at"
  | "has_analysis_snapshot"
>;
export type AnalysisRunSummary = ApiAnalysisRunRecord["summary"];
export type AnalysisResponsePayload = Omit<ApiAnalysisResponse, "calculations"> & {
  calculations: CalculationResponse;
};
export type ProjectAnalysisRun = Omit<ApiAnalysisRunRecord, "analysis"> & {
  analysis: AnalysisResponsePayload;
};
export type ProjectExportEvent = ApiExportEventRecord;
export type ProjectComparison = ApiProjectComparisonResponse;
export type ProjectHistory = ApiProjectHistoryResponse;
export type ProjectRevision = Omit<ApiProjectRevisionRecord, "payload"> & {
  payload: HydratableExperimentInput;
};
export type ProjectRevisionHistory = Omit<ApiProjectRevisionHistoryResponse, "revisions"> & {
  revisions: ProjectRevision[];
};
export type ApiHealthResponse = ApiHealthResponseContract;
export type ApiDiagnosticsResponse = ApiDiagnosticsResponseContract;
export type WorkspaceBundleInput = ApiWorkspaceBundleInput;
export type WorkspaceProjectRecord = Omit<ApiWorkspaceBundleOutput["projects"][number], "payload"> & {
  payload: HydratableExperimentInput;
};
export type WorkspaceProjectRevision = Omit<NonNullable<ApiWorkspaceBundleOutput["project_revisions"]>[number], "payload"> & {
  payload: HydratableExperimentInput;
};
export type WorkspaceBundle = Omit<ApiWorkspaceBundleOutput, "projects" | "project_revisions"> & {
  projects: WorkspaceProjectRecord[];
  project_revisions?: WorkspaceProjectRevision[];
};
export type WorkspaceImportResponse = ApiWorkspaceImportResponse;
export type WorkspaceValidationResponse = ApiWorkspaceValidationResponse;
export type ResultsState = Partial<Pick<AnalysisResponsePayload, "calculations" | "report" | "advice">>;
export type SavedProject = ApiProjectListItem;
export type TemplateRecord = {
  id: string;
  name: string;
  category: string;
  description: string;
  built_in: boolean;
  payload: HydratableExperimentInput;
  tags: string[];
  usage_count: number;
};
export type TemplateDeleteResponse = {
  id: string;
  deleted: true;
};
export type AuditLogEntry = {
  id: number;
  ts: string;
  action: string;
  project_id?: string | null;
  project_name?: string | null;
  actor?: string | null;
  request_id?: string | null;
  payload_diff?: Record<string, [unknown, unknown]> | null;
  ip_address?: string | null;
};
export type AuditLogResponse = {
  entries: AuditLogEntry[];
  total: number;
};
export type ProjectRecordPayload = Omit<ApiProjectRecord, "payload"> & {
  payload: HydratableExperimentInput;
};
export type ExportFormat = "markdown" | "html" | "pdf";
export type FieldKind = "text" | "textarea" | "number" | "boolean";
export type FullPayloadSectionKey = Extract<keyof FullPayload, string>;
export type DraftFieldValue = string | number | boolean | null | GuardrailMetricDraft[];
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
  helpText?: string;
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
export type WizardStepKey = FullPayloadSectionKey | "review";
export type WizardStep = {
  key: WizardStepKey;
  label: string;
  icon?: string;
};
export type FieldDef = SectionField;
export type CalculateRequest = CalculationRequestPayload;
export type AnalyzeRequest = ExperimentInputPayload;
export type DesignRequest = ExperimentInputPayload;
export type ExportRequest = ReportResponse;
export type ExperimentDraft = FullPayload;
export type MetricInput = MetricsDraftSection;
export type VariantConfig = SetupDraftSection;
export type ConstraintsConfig = ConstraintsSection;
export type AnalysisResult = AnalysisResponsePayload;
export type CalculationResult = CalculationResponse;
export type DesignReport = ReportResponse;
export type AiAdvice = AdviceResponse;
export type Project = SavedProject;
export type AnalysisRun = ProjectAnalysisRun;
export type WorkspaceStatus = ApiDiagnosticsResponse;
