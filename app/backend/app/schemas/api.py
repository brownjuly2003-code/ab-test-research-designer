from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.backend.app.constants import MAX_SUPPORTED_VARIANTS
from app.backend.app.schemas.report import ExperimentReport


class ErrorResponse(BaseModel):
    detail: Any
    error_code: str
    status_code: int
    request_id: str


class ProjectContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_name: str
    domain: str
    product_type: str
    platform: str
    market: str
    project_description: str


class HypothesisContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_description: str
    target_audience: str
    business_problem: str
    hypothesis_statement: str
    what_to_validate: str
    desired_result: str


class ExperimentSetup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_type: str
    randomization_unit: str
    traffic_split: list[int] = Field(min_length=2)
    expected_daily_traffic: int = Field(gt=0)
    audience_share_in_test: float = Field(gt=0, le=1)
    variants_count: int = Field(ge=2, le=MAX_SUPPORTED_VARIANTS)
    inclusion_criteria: str
    exclusion_criteria: str

    @model_validator(mode="after")
    def validate_variants(self) -> "ExperimentSetup":
        if len(self.traffic_split) != self.variants_count:
            raise ValueError("traffic_split length must match variants_count")
        if any(weight <= 0 for weight in self.traffic_split):
            raise ValueError("traffic_split must contain positive values")
        return self


class GuardrailMetricInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    metric_type: Literal["binary", "continuous"]
    baseline_rate: float | None = Field(default=None, gt=0, lt=100)
    baseline_mean: float | None = None
    std_dev: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_metric_specific_fields(self) -> "GuardrailMetricInput":
        if self.metric_type == "binary" and self.baseline_rate is None:
            raise ValueError("binary guardrail requires baseline_rate")
        if self.metric_type == "continuous" and (self.baseline_mean is None or self.std_dev is None):
            raise ValueError("continuous guardrail requires baseline_mean and std_dev")
        return self


class MetricsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_metric_name: str
    metric_type: Literal["binary", "continuous"]
    baseline_value: float
    expected_uplift_pct: float | None = None
    mde_pct: float = Field(gt=0)
    alpha: float = Field(gt=0, lt=1)
    power: float = Field(gt=0, lt=1)
    std_dev: float | None = None
    cuped_pre_experiment_std: float | None = Field(default=None, gt=0)
    cuped_correlation: float | None = Field(default=None, gt=-1.0, lt=1.0)
    secondary_metrics: list[str] = Field(default_factory=list)
    guardrail_metrics: list[GuardrailMetricInput] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def validate_metric_specific_fields(self) -> "MetricsConfig":
        if self.metric_type == "binary" and not 0 < self.baseline_value < 1:
            raise ValueError("baseline_value must be between 0 and 1 for binary metrics")
        if self.metric_type == "continuous":
            if self.baseline_value <= 0:
                raise ValueError("baseline_value must be positive for continuous metrics")
            if self.std_dev is None or self.std_dev <= 0:
                raise ValueError("std_dev must be positive for continuous metrics")
        return self


class ConstraintsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seasonality_present: bool
    active_campaigns_present: bool
    returning_users_present: bool
    interference_risk: str
    technical_constraints: str
    legal_or_ethics_constraints: str
    known_risks: str
    deadline_pressure: str
    long_test_possible: bool
    n_looks: int = Field(default=1, ge=1, le=10)
    analysis_mode: Literal["frequentist", "bayesian"] = "frequentist"
    desired_precision: float | None = Field(default=None, gt=0)
    credibility: float = Field(default=0.95, gt=0.5, lt=1.0)

    @model_validator(mode="after")
    def validate_analysis_mode(self) -> "ConstraintsConfig":
        if self.analysis_mode == "bayesian" and self.desired_precision is None:
            raise ValueError("Bayesian mode requires desired_precision")
        return self


class ObservedResultsBinary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control_conversions: int = Field(ge=0)
    control_users: int = Field(ge=1)
    treatment_conversions: int = Field(ge=0)
    treatment_users: int = Field(ge=1)
    alpha: float = Field(default=0.05, ge=0.001, le=0.1)

    @model_validator(mode="after")
    def validate_counts(self) -> "ObservedResultsBinary":
        if self.control_conversions > self.control_users:
            raise ValueError("control_conversions cannot exceed control_users")
        if self.treatment_conversions > self.treatment_users:
            raise ValueError("treatment_conversions cannot exceed treatment_users")
        return self


class ObservedResultsContinuous(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control_mean: float
    control_std: float = Field(gt=0)
    control_n: int = Field(ge=1)
    treatment_mean: float
    treatment_std: float = Field(gt=0)
    treatment_n: int = Field(ge=1)
    alpha: float = Field(default=0.05, ge=0.001, le=0.1)


class ResultsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_type: Literal["binary", "continuous"]
    binary: ObservedResultsBinary | None = None
    continuous: ObservedResultsContinuous | None = None

    @model_validator(mode="after")
    def check_type(self) -> "ResultsRequest":
        if self.metric_type == "binary":
            if self.binary is None:
                raise ValueError("binary metric_type requires binary data")
            if self.continuous is not None:
                raise ValueError("binary metric_type does not accept continuous data")
        if self.metric_type == "continuous":
            if self.continuous is None:
                raise ValueError("continuous metric_type requires continuous data")
            if self.binary is not None:
                raise ValueError("continuous metric_type does not accept binary data")
        return self


class ResultsResponse(BaseModel):
    metric_type: str
    observed_effect: float
    observed_effect_relative: float
    control_rate: float | None = None
    treatment_rate: float | None = None
    ci_lower: float
    ci_upper: float
    ci_level: float
    p_value: float
    test_statistic: float
    is_significant: bool
    power_achieved: float
    verdict: str
    interpretation: str


class SavedObservedResults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: ResultsRequest
    analysis: ResultsResponse
    saved_at: str | None = None


class AdditionalContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_context: str = ""
    observed_results: SavedObservedResults | None = None


class ExperimentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: ProjectContext
    hypothesis: HypothesisContext
    setup: ExperimentSetup
    metrics: MetricsConfig
    constraints: ConstraintsConfig
    additional_context: AdditionalContext = Field(default_factory=AdditionalContext)


class CalculationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_type: Literal["binary", "continuous"]
    baseline_value: float
    std_dev: float | None = None
    cuped_pre_experiment_std: float | None = Field(default=None, gt=0)
    cuped_correlation: float | None = Field(default=None, gt=-1.0, lt=1.0)
    mde_pct: float = Field(gt=0)
    alpha: float = Field(gt=0, lt=1)
    power: float = Field(gt=0, lt=1)
    expected_daily_traffic: int = Field(gt=0)
    audience_share_in_test: float = Field(gt=0, le=1)
    traffic_split: list[int] = Field(min_length=2)
    variants_count: int = Field(ge=2, le=MAX_SUPPORTED_VARIANTS)
    actual_counts: list[int] | None = Field(default=None, min_length=2, max_length=MAX_SUPPORTED_VARIANTS)
    seasonality_present: bool | None = None
    active_campaigns_present: bool | None = None
    long_test_possible: bool | None = None
    n_looks: int = Field(default=1, ge=1, le=10)
    analysis_mode: Literal["frequentist", "bayesian"] = "frequentist"
    desired_precision: float | None = Field(default=None, gt=0)
    credibility: float = Field(default=0.95, gt=0.5, lt=1.0)

    @model_validator(mode="after")
    def validate_variants(self) -> "CalculationRequest":
        if len(self.traffic_split) != self.variants_count:
            raise ValueError("traffic_split length must match variants_count")
        if any(weight <= 0 for weight in self.traffic_split):
            raise ValueError("traffic_split must contain positive values")
        return self

    @model_validator(mode="after")
    def validate_metric_specific_fields(self) -> "CalculationRequest":
        if self.metric_type == "binary" and not 0 < self.baseline_value < 1:
            raise ValueError("baseline_value must be between 0 and 1 for binary metrics")
        if self.metric_type == "continuous":
            if self.baseline_value <= 0:
                raise ValueError("baseline_value must be positive for continuous metrics")
            if self.std_dev is None or self.std_dev <= 0:
                raise ValueError("std_dev must be positive for continuous metrics")
        return self

    @model_validator(mode="after")
    def validate_actual_counts(self) -> "CalculationRequest":
        if self.actual_counts is None:
            return self
        if len(self.actual_counts) != self.variants_count:
            raise ValueError("actual_counts length must match variants_count")
        if any(count < 0 for count in self.actual_counts):
            raise ValueError("actual_counts must be non-negative")
        if sum(self.actual_counts) <= 0:
            raise ValueError("actual_counts must sum to a positive total")
        return self

    @model_validator(mode="after")
    def validate_analysis_mode(self) -> "CalculationRequest":
        if self.analysis_mode == "bayesian" and self.desired_precision is None:
            raise ValueError("Bayesian mode requires desired_precision")
        return self


class SensitivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_type: Literal["binary", "continuous"]
    baseline_rate: float | None = None
    baseline_mean: float | None = None
    std_dev: float | None = None
    variants: int = Field(ge=2, le=MAX_SUPPORTED_VARIANTS, default=2)
    alpha: float = Field(gt=0, lt=1, default=0.05)
    daily_traffic: float = Field(gt=0, default=1000.0)
    audience_share: float = Field(gt=0, le=1, default=1.0)
    traffic_split: list[float] | None = None
    mde_values: list[float] = Field(default_factory=lambda: [0.1, 0.5, 1.0, 2.0, 5.0], min_length=1)
    power_values: list[float] = Field(default_factory=lambda: [0.7, 0.8, 0.9, 0.95], min_length=1)

    @model_validator(mode="after")
    def validate_metric_specific_fields(self) -> "SensitivityRequest":
        if self.metric_type == "binary":
            if self.baseline_rate is None or not 0 < self.baseline_rate < 100:
                raise ValueError("baseline_rate must be between 0 and 100 for binary metrics")
        if self.metric_type == "continuous":
            if self.baseline_mean is None or self.baseline_mean <= 0:
                raise ValueError("baseline_mean must be positive for continuous metrics")
            if self.std_dev is None or self.std_dev <= 0:
                raise ValueError("std_dev must be positive for continuous metrics")
        if any(value <= 0 for value in self.mde_values):
            raise ValueError("mde_values must contain positive values")
        if any(value <= 0 or value >= 1 for value in self.power_values):
            raise ValueError("power_values must contain values between 0 and 1")
        return self

    @model_validator(mode="after")
    def validate_traffic_split(self) -> "SensitivityRequest":
        if self.traffic_split is None:
            self.traffic_split = [1.0] * self.variants
            return self
        if len(self.traffic_split) != self.variants:
            raise ValueError("traffic_split length must match variants")
        if any(weight <= 0 for weight in self.traffic_split):
            raise ValueError("traffic_split must contain positive values")
        return self


class SensitivityCell(BaseModel):
    mde: float
    power: float
    sample_size_per_variant: int
    duration_days: float


class SensitivityResponse(BaseModel):
    cells: list[SensitivityCell]
    current_mde: float | None = None
    current_power: float | None = None


class SrmCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_counts: list[int] = Field(min_length=2, max_length=MAX_SUPPORTED_VARIANTS)
    expected_fractions: list[float] = Field(min_length=2, max_length=MAX_SUPPORTED_VARIANTS)

    @model_validator(mode="after")
    def validate_lengths_and_fractions(self) -> "SrmCheckRequest":
        if len(self.observed_counts) != len(self.expected_fractions):
            raise ValueError("observed_counts and expected_fractions must have same length")
        if any(count < 0 for count in self.observed_counts):
            raise ValueError("observed_counts must be non-negative")
        if any(fraction < 0 for fraction in self.expected_fractions):
            raise ValueError("expected_fractions must be non-negative")
        total_fraction = sum(self.expected_fractions)
        if abs(total_fraction - 1.0) > 0.01:
            raise ValueError(f"expected_fractions must sum to 1.0, got {total_fraction:.4f}")
        return self


class SrmCheckResponse(BaseModel):
    chi_square: float
    p_value: float
    is_srm: bool
    verdict: str
    observed_counts: list[int]
    expected_counts: list[float]


class WarningResponse(BaseModel):
    code: str
    severity: str
    message: str
    source: str


class CalculationSummaryResponse(BaseModel):
    metric_type: str
    baseline_value: float
    mde_pct: float
    mde_absolute: float
    alpha: float
    power: float


class CalculationResultsResponse(BaseModel):
    sample_size_per_variant: int
    total_sample_size: int
    effective_daily_traffic: float
    estimated_duration_days: int


class CalculationResponse(BaseModel):
    calculation_summary: CalculationSummaryResponse
    results: CalculationResultsResponse
    assumptions: list[str]
    warnings: list[WarningResponse]
    bonferroni_note: str | None = None
    bayesian_sample_size_per_variant: int | None = None
    bayesian_credibility: float | None = None
    bayesian_note: str | None = None
    sequential_boundaries: list[dict[str, Any]] | None = None
    sequential_inflation_factor: float | None = None
    sequential_adjusted_sample_size: int | None = None
    cuped_std: float | None = None
    cuped_sample_size_per_variant: int | None = None
    cuped_variance_reduction_pct: float | None = None
    cuped_duration_days: float | None = None


class AdvicePayload(BaseModel):
    brief_assessment: str
    key_risks: list[str]
    design_improvements: list[str]
    metric_recommendations: list[str]
    interpretation_pitfalls: list[str]
    additional_checks: list[str]


class LlmAdviceRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    project_context: dict[str, Any]
    hypothesis: dict[str, Any] | None = None
    setup: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    constraints: dict[str, Any] | None = None
    additional_context: dict[str, Any] | None = None
    calculation_results: dict[str, Any] | None = None
    warnings: list[dict[str, Any]] | None = None


class LlmAdviceResponse(BaseModel):
    available: bool
    provider: str
    model: str
    advice: AdvicePayload | None
    raw_text: str | None
    error: str | None
    error_code: str | None = None


class AnalysisResponse(BaseModel):
    calculations: CalculationResponse
    report: ExperimentReport
    advice: LlmAdviceResponse


class AnalysisRunSummary(BaseModel):
    metric_type: str | None = None
    sample_size_per_variant: int | None = None
    total_sample_size: int | None = None
    estimated_duration_days: int | None = None
    warnings_count: int = 0
    advice_available: bool = False


class AnalysisRunRecord(BaseModel):
    id: str
    project_id: str
    created_at: str
    summary: AnalysisRunSummary
    analysis: AnalysisResponse


class ExportEventRecord(BaseModel):
    id: str
    project_id: str
    analysis_run_id: str | None = None
    format: Literal["markdown", "html", "pdf"]
    created_at: str


class ProjectRevisionRecord(BaseModel):
    id: str
    project_id: str
    source: Literal["create", "update", "workspace_import"]
    created_at: str
    payload: ExperimentInput


class ProjectHistoryResponse(BaseModel):
    project_id: str
    analysis_total: int
    analysis_limit: int
    analysis_offset: int
    export_total: int
    export_limit: int
    export_offset: int
    analysis_runs: list[AnalysisRunRecord]
    export_events: list[ExportEventRecord]


class ProjectRevisionHistoryResponse(BaseModel):
    project_id: str
    total: int
    limit: int
    offset: int
    revisions: list[ProjectRevisionRecord]


class ProjectComparisonItem(BaseModel):
    id: str
    project_name: str
    updated_at: str
    analysis_created_at: str
    last_analysis_at: str | None = None
    analysis_run_id: str
    metric_type: str
    primary_metric: str
    sample_size_per_variant: int
    total_sample_size: int
    estimated_duration_days: int
    warnings_count: int
    warning_codes: list[str]
    risk_highlights: list[str]
    assumptions: list[str]
    advice_available: bool
    executive_summary: str
    warning_severity: str
    recommendation_highlights: list[str]


class ProjectComparisonDelta(BaseModel):
    sample_size_per_variant: int
    total_sample_size: int
    estimated_duration_days: int
    warnings_count: int


class ProjectComparisonResponse(BaseModel):
    base_project: ProjectComparisonItem
    candidate_project: ProjectComparisonItem
    deltas: ProjectComparisonDelta
    shared_warning_codes: list[str]
    base_only_warning_codes: list[str]
    candidate_only_warning_codes: list[str]
    shared_assumptions: list[str]
    base_only_assumptions: list[str]
    candidate_only_assumptions: list[str]
    shared_risk_highlights: list[str]
    base_only_risk_highlights: list[str]
    candidate_only_risk_highlights: list[str]
    metric_alignment_note: str
    highlights: list[str]
    summary: str


class DiagnosticsStorageSummary(BaseModel):
    db_path: str
    db_parent_path: str
    db_exists: bool
    db_size_bytes: int
    disk_free_bytes: int
    schema_version: int
    sqlite_user_version: int
    busy_timeout_ms: int
    journal_mode: str
    synchronous: str
    write_probe_ok: bool
    write_probe_detail: str
    projects_total: int
    archived_projects_total: int
    analysis_runs_total: int
    export_events_total: int
    project_revisions_total: int
    workspace_bundle_schema_version: int
    workspace_signature_enabled: bool
    latest_project_updated_at: str | None = None


class DiagnosticsFrontendSummary(BaseModel):
    serve_frontend_dist: bool
    dist_path: str
    dist_exists: bool


class DiagnosticsLlmSummary(BaseModel):
    provider: str
    base_url: str
    timeout_seconds: float
    max_attempts: int
    initial_backoff_seconds: float
    backoff_multiplier: float


class DiagnosticsLoggingSummary(BaseModel):
    level: str
    format: str


class DiagnosticsAuthSummary(BaseModel):
    enabled: bool
    mode: str
    write_enabled: bool
    readonly_enabled: bool
    accepted_headers: list[str]
    read_only_methods: list[str]


class DiagnosticsGuardsSummary(BaseModel):
    security_headers_enabled: bool
    rate_limit_enabled: bool
    rate_limit_requests: int
    rate_limit_window_seconds: int
    auth_failure_limit: int
    auth_failure_window_seconds: int
    max_request_body_bytes: int
    max_workspace_body_bytes: int


class DiagnosticsRuntimeSummary(BaseModel):
    total_requests: int
    success_responses: int
    client_error_responses: int
    server_error_responses: int
    auth_rejections: int
    rate_limited_responses: int = 0
    request_body_rejections: int = 0
    last_request_at: str | None = None
    last_error_at: str | None = None
    last_error_code: str | None = None


class DiagnosticsResponse(BaseModel):
    status: str
    generated_at: str
    started_at: str
    uptime_seconds: float
    environment: str
    app_version: str
    request_timing_headers_enabled: bool
    storage: DiagnosticsStorageSummary
    frontend: DiagnosticsFrontendSummary
    llm: DiagnosticsLlmSummary
    logging: DiagnosticsLoggingSummary
    auth: DiagnosticsAuthSummary
    guards: DiagnosticsGuardsSummary
    runtime: DiagnosticsRuntimeSummary


class ReadinessCheck(BaseModel):
    name: str
    ok: bool
    detail: str


class ReadinessResponse(BaseModel):
    status: str
    generated_at: str
    checks: list[ReadinessCheck]


class WorkspaceProjectRecord(BaseModel):
    id: str
    project_name: str
    payload_schema_version: int
    archived_at: str | None = None
    last_analysis_at: str | None = None
    last_analysis_run_id: str | None = None
    last_exported_at: str | None = None
    created_at: str
    updated_at: str
    payload: ExperimentInput


class WorkspaceAnalysisRunRecord(BaseModel):
    id: str
    project_id: str
    created_at: str
    analysis: AnalysisResponse


class WorkspaceExportEventRecord(BaseModel):
    id: str
    project_id: str
    analysis_run_id: str | None = None
    format: Literal["markdown", "html", "pdf"]
    created_at: str


class WorkspaceProjectRevisionRecord(BaseModel):
    id: str
    project_id: str
    source: Literal["create", "update", "workspace_import"]
    created_at: str
    payload: ExperimentInput


class WorkspaceIntegrityCounts(BaseModel):
    projects: int
    analysis_runs: int
    export_events: int
    project_revisions: int


class WorkspaceIntegrity(BaseModel):
    counts: WorkspaceIntegrityCounts
    checksum_sha256: str
    signature_hmac_sha256: str | None = None


class WorkspaceValidationResponse(BaseModel):
    status: Literal["valid"]
    schema_version: int
    counts: WorkspaceIntegrityCounts
    checksum_sha256: str
    signature_verified: bool = False


class WorkspaceBundle(BaseModel):
    schema_version: int = 3
    generated_at: str
    projects: list[WorkspaceProjectRecord]
    analysis_runs: list[WorkspaceAnalysisRunRecord]
    export_events: list[WorkspaceExportEventRecord]
    project_revisions: list[WorkspaceProjectRevisionRecord] = Field(default_factory=list)
    integrity: WorkspaceIntegrity | None = None


class WorkspaceImportResponse(BaseModel):
    status: str
    imported_projects: int
    imported_analysis_runs: int
    imported_export_events: int
    imported_project_revisions: int = 0


class ProjectRecord(BaseModel):
    id: str
    project_name: str
    payload_schema_version: int
    archived_at: str | None = None
    is_archived: bool = False
    revision_count: int = 0
    last_revision_at: str | None = None
    last_analysis_at: str | None = None
    last_analysis_run_id: str | None = None
    last_exported_at: str | None = None
    has_analysis_snapshot: bool = False
    created_at: str
    updated_at: str
    payload: ExperimentInput


class ProjectListItem(BaseModel):
    id: str
    project_name: str
    hypothesis: str | None = None
    metric_type: Literal["binary", "continuous"] | None = None
    duration_days: int | None = None
    payload_schema_version: int
    archived_at: str | None = None
    is_archived: bool = False
    revision_count: int = 0
    last_revision_at: str | None = None
    last_analysis_at: str | None = None
    last_analysis_run_id: str | None = None
    last_exported_at: str | None = None
    has_analysis_snapshot: bool = False
    created_at: str
    updated_at: str


class ProjectListResponse(BaseModel):
    projects: list[ProjectListItem]
    total: int = 0
    offset: int = 0
    limit: int = 50
    has_more: bool = False


class ProjectArchiveResponse(BaseModel):
    id: str
    archived: bool
    archived_at: str | None = None


class ProjectDeleteResponse(BaseModel):
    id: str
    deleted: bool


class ProjectExportMarkRequest(BaseModel):
    format: Literal["markdown", "html", "pdf"]
    analysis_run_id: str | None = None


class StandaloneExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_name: str
    hypothesis: str | None = None
    calculation: dict[str, Any]
    design: dict[str, Any]
    ai_advice: dict[str, Any] | None = None
    sensitivity: dict[str, Any] | None = None
    results: dict[str, Any] | None = None


class ExportResponse(BaseModel):
    content: str


__all__ = [
    "AnalysisResponse",
    "CalculationRequest",
    "CalculationResponse",
    "DiagnosticsResponse",
    "ErrorResponse",
    "ExperimentInput",
    "ExperimentReport",
    "ExportResponse",
    "GuardrailMetricInput",
    "ProjectArchiveResponse",
    "ProjectComparisonResponse",
    "ProjectHistoryResponse",
    "ProjectRevisionHistoryResponse",
    "LlmAdviceRequest",
    "LlmAdviceResponse",
    "ProjectDeleteResponse",
    "ProjectExportMarkRequest",
    "ProjectListResponse",
    "ProjectRecord",
    "ReadinessResponse",
    "ResultsRequest",
    "ResultsResponse",
    "SensitivityCell",
    "SensitivityRequest",
    "SensitivityResponse",
    "SrmCheckRequest",
    "SrmCheckResponse",
    "StandaloneExportRequest",
    "WorkspaceBundle",
    "WorkspaceImportResponse",
    "WorkspaceValidationResponse",
]
