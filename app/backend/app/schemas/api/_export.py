"""Export request/response payloads."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.backend.app.schemas.api._projects import MultiProjectComparisonRequest


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


class ComparisonExportRequest(MultiProjectComparisonRequest):
    format: Literal["pdf", "markdown"]
