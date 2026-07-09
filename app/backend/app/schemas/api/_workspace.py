"""Workspace backup bundle payloads."""

from typing import Literal

from pydantic import BaseModel, Field

from app.backend.app.schemas.api._experiment import ExperimentInput
from app.backend.app.schemas.api._projects import AnalysisResponse


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
