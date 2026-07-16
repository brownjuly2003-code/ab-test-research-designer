"""Saved projects, their history, and cross-project comparison."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.backend.app.constants import MetricType
from app.backend.app.schemas.api._calculation import (
    CalculationResponse,
    SensitivityResponse,
)
from app.backend.app.schemas.api._experiment import ExperimentInput
from app.backend.app.schemas.api._llm import LlmAdviceResponse
from app.backend.app.schemas.api._results import ResultsResponse
from app.backend.app.schemas.report import ExperimentReport


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
    sensitivity: SensitivityResponse | None = None
    observed_results: ResultsResponse | None = None


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


class MultiProjectComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_ids: list[str] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def validate_project_ids(self) -> "MultiProjectComparisonRequest":
        normalized_ids: list[str] = []
        seen: set[str] = set()
        for project_id in self.project_ids:
            cleaned = project_id.strip()
            if not cleaned:
                raise ValueError("project_ids must not contain empty values")
            if cleaned in seen:
                raise ValueError("project_ids must be unique")
            seen.add(cleaned)
            normalized_ids.append(cleaned)
        self.project_ids = normalized_ids
        return self


class ComparisonRangeSummary(BaseModel):
    min: int
    max: int
    median: float


class ProjectUniqueInsights(BaseModel):
    warnings: list[str]
    risks: list[str]
    assumptions: list[str]


class MonteCarloSimulationResponse(BaseModel):
    num_simulations: int
    percentiles: dict[str, float]
    probability_uplift_positive: float
    probability_uplift_above_threshold: dict[str, float]
    simulated_uplifts: list[float]


class MultiProjectComparisonResponse(BaseModel):
    projects: list[ProjectComparisonItem]
    shared_warnings: list[str]
    shared_risks: list[str]
    shared_assumptions: list[str]
    unique_per_project: dict[str, ProjectUniqueInsights]
    sample_size_range: ComparisonRangeSummary
    duration_range: ComparisonRangeSummary
    metric_types_used: list[str]
    recommendation_highlights: list[str]
    monte_carlo_distribution: dict[str, MonteCarloSimulationResponse] | None = None

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
    metric_type: MetricType | None = None
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
