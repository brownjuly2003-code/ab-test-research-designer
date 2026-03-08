from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.backend.app.constants import MAX_SUPPORTED_VARIANTS
from app.backend.app.schemas.report import ExperimentReport


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
    secondary_metrics: list[str] = Field(default_factory=list)
    guardrail_metrics: list[str] = Field(default_factory=list)

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


class AdditionalContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_context: str = ""


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
    mde_pct: float = Field(gt=0)
    alpha: float = Field(gt=0, lt=1)
    power: float = Field(gt=0, lt=1)
    expected_daily_traffic: int = Field(gt=0)
    audience_share_in_test: float = Field(gt=0, le=1)
    traffic_split: list[int] = Field(min_length=2)
    variants_count: int = Field(ge=2, le=MAX_SUPPORTED_VARIANTS)
    seasonality_present: bool | None = None
    active_campaigns_present: bool | None = None
    long_test_possible: bool | None = None

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
    format: Literal["markdown", "html"]
    created_at: str


class ProjectHistoryResponse(BaseModel):
    project_id: str
    analysis_runs: list[AnalysisRunRecord]
    export_events: list[ExportEventRecord]


class ProjectComparisonItem(BaseModel):
    id: str
    project_name: str
    updated_at: str
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
    summary: str


class ProjectRecord(BaseModel):
    id: str
    project_name: str
    payload_schema_version: int
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
    payload_schema_version: int
    last_analysis_at: str | None = None
    last_analysis_run_id: str | None = None
    last_exported_at: str | None = None
    has_analysis_snapshot: bool = False
    created_at: str
    updated_at: str


class ProjectListResponse(BaseModel):
    projects: list[ProjectListItem]


class ProjectDeleteResponse(BaseModel):
    id: str
    deleted: bool


class ProjectExportMarkRequest(BaseModel):
    format: Literal["markdown", "html"]
    analysis_run_id: str | None = None


class ExportResponse(BaseModel):
    content: str


__all__ = [
    "AnalysisResponse",
    "CalculationRequest",
    "CalculationResponse",
    "ExperimentInput",
    "ExperimentReport",
    "ExportResponse",
    "ProjectComparisonResponse",
    "ProjectHistoryResponse",
    "LlmAdviceRequest",
    "LlmAdviceResponse",
    "ProjectDeleteResponse",
    "ProjectExportMarkRequest",
    "ProjectListResponse",
    "ProjectRecord",
]
