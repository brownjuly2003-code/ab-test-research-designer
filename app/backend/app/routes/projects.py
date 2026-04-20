from fastapi import APIRouter, Depends, HTTPException, Query

from app.backend.app.schemas.api import (
    AnalysisResponse,
    ExperimentInput,
    ProjectArchiveResponse,
    ProjectComparisonResponse,
    ProjectDeleteResponse,
    ProjectExportMarkRequest,
    ProjectHistoryResponse,
    ProjectListResponse,
    ProjectRecord,
    ProjectRevisionHistoryResponse,
)
from app.backend.app.services.comparison_service import build_project_comparison


def _project_snapshot_placeholder() -> None:
    raise NotImplementedError("Project snapshot placeholder")


def create_projects_router(settings, repository, rate_limiter, require_auth, require_write_auth) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/v1/projects",
        response_model=ProjectListResponse,
        dependencies=[Depends(require_auth)],
    )
    def list_projects(include_archived: bool = Query(default=False)) -> ProjectListResponse:
        return ProjectListResponse.model_validate(
            {"projects": repository.list_projects(include_archived=include_archived)}
        )

    @router.post(
        "/api/v1/projects",
        response_model=ProjectRecord,
        dependencies=[Depends(require_write_auth)],
    )
    def create_project(payload: ExperimentInput) -> ProjectRecord:
        project = repository.create_project(payload.model_dump())
        return ProjectRecord.model_validate(project)

    @router.get(
        "/api/v1/projects/compare",
        response_model=ProjectComparisonResponse,
        dependencies=[Depends(require_auth)],
    )
    def compare_projects(
        base_id: str,
        candidate_id: str,
        base_run_id: str | None = None,
        candidate_run_id: str | None = None,
    ) -> ProjectComparisonResponse:
        if base_id == candidate_id:
            raise ValueError("base_id and candidate_id must be different")
        base_project = repository.get_project(base_id)
        if base_project is None:
            raise HTTPException(status_code=404, detail="Base project not found")
        candidate_project = repository.get_project(candidate_id)
        if candidate_project is None:
            raise HTTPException(status_code=404, detail="Candidate project not found")
        base_analysis_run = (
            repository.get_analysis_run(base_id, base_run_id)
            if base_run_id is not None
            else repository.get_latest_analysis_run(base_id)
        )
        if base_analysis_run is None:
            if base_run_id is not None:
                raise HTTPException(status_code=404, detail="Base analysis run not found")
            raise ValueError("Base project has no saved analysis snapshot")
        candidate_analysis_run = (
            repository.get_analysis_run(candidate_id, candidate_run_id)
            if candidate_run_id is not None
            else repository.get_latest_analysis_run(candidate_id)
        )
        if candidate_analysis_run is None:
            if candidate_run_id is not None:
                raise HTTPException(status_code=404, detail="Candidate analysis run not found")
            raise ValueError("Candidate project has no saved analysis snapshot")
        comparison = build_project_comparison(
            base_project,
            base_analysis_run,
            candidate_project,
            candidate_analysis_run,
        )
        return ProjectComparisonResponse.model_validate(comparison)

    @router.get(
        "/api/v1/projects/{project_id}",
        response_model=ProjectRecord,
        dependencies=[Depends(require_auth)],
    )
    def get_project(project_id: str) -> ProjectRecord:
        project = repository.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectRecord.model_validate(project)

    @router.put(
        "/api/v1/projects/{project_id}",
        response_model=ProjectRecord,
        dependencies=[Depends(require_write_auth)],
    )
    def update_project(project_id: str, payload: ExperimentInput) -> ProjectRecord:
        project = repository.update_project(project_id, payload.model_dump())
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectRecord.model_validate(project)

    @router.get(
        "/api/v1/projects/{project_id}/history",
        response_model=ProjectHistoryResponse,
        dependencies=[Depends(require_auth)],
    )
    def get_project_history(
        project_id: str,
        analysis_limit: int = Query(default=20, ge=1, le=100),
        analysis_offset: int = Query(default=0, ge=0),
        export_limit: int = Query(default=20, ge=1, le=100),
        export_offset: int = Query(default=0, ge=0),
    ) -> ProjectHistoryResponse:
        history = repository.get_project_history(
            project_id,
            analysis_limit=analysis_limit,
            analysis_offset=analysis_offset,
            export_limit=export_limit,
            export_offset=export_offset,
        )
        if history is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectHistoryResponse.model_validate(history)

    @router.get(
        "/api/v1/projects/{project_id}/revisions",
        response_model=ProjectRevisionHistoryResponse,
        dependencies=[Depends(require_auth)],
    )
    def get_project_revisions(
        project_id: str,
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> ProjectRevisionHistoryResponse:
        revisions = repository.get_project_revisions(project_id, limit=limit, offset=offset)
        if revisions is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectRevisionHistoryResponse.model_validate(revisions)

    @router.post(
        "/api/v1/projects/{project_id}/analysis",
        response_model=ProjectRecord,
        dependencies=[Depends(require_write_auth)],
    )
    def record_project_analysis(project_id: str, payload: AnalysisResponse) -> ProjectRecord:
        project = repository.record_analysis(project_id, payload.model_dump())
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectRecord.model_validate(project)

    @router.post(
        "/api/v1/projects/{project_id}/exports",
        response_model=ProjectRecord,
        dependencies=[Depends(require_write_auth)],
    )
    def record_project_export(project_id: str, payload: ProjectExportMarkRequest) -> ProjectRecord:
        project = repository.record_export(project_id, payload.format, payload.analysis_run_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectRecord.model_validate(project)

    @router.post(
        "/api/v1/projects/{project_id}/archive",
        response_model=ProjectArchiveResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def archive_project(project_id: str) -> ProjectArchiveResponse:
        archived = repository.archive_project(project_id)
        if not archived:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectArchiveResponse.model_validate(archived)

    @router.delete(
        "/api/v1/projects/{project_id}",
        response_model=ProjectDeleteResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def delete_project(project_id: str) -> ProjectDeleteResponse:
        deleted = repository.delete_project(project_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectDeleteResponse.model_validate(deleted)

    @router.post(
        "/api/v1/projects/{project_id}/restore",
        response_model=ProjectRecord,
        dependencies=[Depends(require_write_auth)],
    )
    def restore_project(project_id: str) -> ProjectRecord:
        project = repository.restore_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectRecord.model_validate(project)

    return router
