import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from app.backend.app.schemas.api import (
    AnalysisResponse,
    ExperimentInput,
    MultiProjectComparisonRequest,
    MultiProjectComparisonResponse,
    ProjectArchiveResponse,
    ProjectComparisonResponse,
    ProjectDeleteResponse,
    ProjectExportMarkRequest,
    ProjectHistoryResponse,
    ProjectListResponse,
    ProjectRecord,
    ProjectRevisionHistoryResponse,
)
from app.backend.app.services.comparison_service import build_multi_project_comparison, build_project_comparison
from app.backend.app.services.export_service import (
    export_project_report_to_csv,
    export_project_report_to_xlsx,
)
from app.backend.app.services.monte_carlo_service import simulate_comparison
from app.backend.app.services.pdf_service import generate_report_pdf


def _project_snapshot_placeholder() -> None:
    raise NotImplementedError("Project snapshot placeholder")


def _slugify_filename(value: str) -> str:
    sanitized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    cleaned = sanitized.strip("-")
    return cleaned or "ab-test-report"


def _resolve_audit_actor(request: Request) -> str:
    actor = getattr(request.state, "audit_actor", None)
    if isinstance(actor, str) and actor:
        return actor
    auth_scope = getattr(request.state, "auth_scope", None)
    if auth_scope in {"write", "admin"}:
        return "api_key:rw"
    if auth_scope == "read":
        return "api_key:ro"
    return "anonymous"


def _request_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def create_projects_router(settings, repository, rate_limiter, require_auth, require_write_auth) -> APIRouter:
    router = APIRouter(tags=["projects"])

    @router.get(
        "/api/v1/projects",
        response_model=ProjectListResponse,
        dependencies=[Depends(require_auth)],
    )
    def list_projects(
        include_archived: bool | None = Query(default=None),
        q: str | None = Query(default=None),
        status: Literal["active", "archived", "all"] = "active",
        metric_type: Literal["binary", "continuous", "all"] = "all",
        sort_by: Literal["created_at", "updated_at", "name", "duration_days"] = "updated_at",
        sort_dir: Literal["asc", "desc"] = "desc",
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> ProjectListResponse:
        resolved_status = "all" if include_archived is True and status == "active" else status
        return ProjectListResponse.model_validate(
            repository.query_projects(
                q=q,
                status=resolved_status,
                metric_type=metric_type,
                sort_by=sort_by,
                sort_dir=sort_dir,
                limit=limit,
                offset=offset,
            )
        )

    @router.post(
        "/api/v1/projects",
        response_model=ProjectRecord,
        dependencies=[Depends(require_write_auth)],
    )
    def create_project(request: Request, payload: ExperimentInput) -> ProjectRecord:
        project = repository.create_project(payload.model_dump())
        repository.log_audit_entry(
            action="project.create",
            project_id=project["id"],
            project_name=project["project_name"],
            key_id=getattr(request.state, "auth_key_id", None),
            actor=_resolve_audit_actor(request),
            request_id=getattr(request.state, "request_id", None),
            ip_address=_request_ip(request),
        )
        return ProjectRecord.model_validate(project)

    @router.get(
        "/api/v1/projects/compare",
        response_model=ProjectComparisonResponse,
        dependencies=[Depends(require_auth)],
    )
    def compare_projects(
        response: Response,
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
        response.headers["Deprecation"] = "true"
        return ProjectComparisonResponse.model_validate(comparison)

    @router.post(
        "/api/v1/projects/compare",
        response_model=MultiProjectComparisonResponse,
        dependencies=[Depends(require_auth)],
    )
    def compare_multiple_projects(
        payload: MultiProjectComparisonRequest,
        include_monte_carlo: bool = Query(default=False),
        monte_carlo_simulations: int = Query(default=10000, ge=1000, le=50000),
    ) -> JSONResponse:
        projects_with_runs: list[tuple[dict, dict]] = []
        project_records: list[dict] = []
        for project_id in payload.project_ids:
            project = repository.get_project(project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="Project not found")
            analysis_run = repository.get_latest_analysis_run(project_id)
            if analysis_run is None:
                raise HTTPException(status_code=404, detail="Project analysis snapshot not found")
            project_records.append(project)
            projects_with_runs.append((project, analysis_run))
        comparison = build_multi_project_comparison(projects_with_runs)
        if include_monte_carlo:
            comparison["monte_carlo_distribution"] = simulate_comparison(
                project_records,
                num_simulations=monte_carlo_simulations,
                seed=None,
            )
        response_payload = MultiProjectComparisonResponse.model_validate(comparison).model_dump(mode="json")
        if not include_monte_carlo:
            response_payload.pop("monte_carlo_distribution", None)
        return JSONResponse(content=response_payload)

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

    @router.get(
        "/api/v1/projects/{project_id}/report/pdf",
        dependencies=[Depends(require_auth)],
    )
    def get_project_report_pdf(project_id: str) -> Response:
        project = repository.get_project(project_id, include_archived=True)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        analysis_run = repository.get_latest_analysis_run(project_id)
        if analysis_run is None:
            raise HTTPException(status_code=404, detail="Project report not found")
        revisions = repository.get_project_revisions(project_id, limit=8, offset=0)
        filename = f"{_slugify_filename(project['project_name'])}-report.pdf"
        pdf_bytes = generate_report_pdf(
            project,
            analysis_run["analysis"],
            [] if revisions is None else revisions["revisions"],
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.get(
        "/api/v1/projects/{project_id}/report/csv",
        dependencies=[Depends(require_auth)],
    )
    def get_project_report_csv(project_id: str) -> Response:
        project = repository.get_project(project_id, include_archived=True)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        analysis_run = repository.get_latest_analysis_run(project_id)
        if analysis_run is None:
            raise HTTPException(status_code=404, detail="Project report not found")
        filename = f"{_slugify_filename(project['project_name'])}-report.csv"
        return Response(
            content=export_project_report_to_csv(project, analysis_run["analysis"]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.get(
        "/api/v1/projects/{project_id}/report/xlsx",
        dependencies=[Depends(require_auth)],
    )
    def get_project_report_xlsx(project_id: str) -> Response:
        project = repository.get_project(project_id, include_archived=True)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        analysis_run = repository.get_latest_analysis_run(project_id)
        if analysis_run is None:
            raise HTTPException(status_code=404, detail="Project report not found")
        filename = f"{_slugify_filename(project['project_name'])}-report.xlsx"
        return Response(
            content=export_project_report_to_xlsx(project, analysis_run["analysis"]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.put(
        "/api/v1/projects/{project_id}",
        response_model=ProjectRecord,
        dependencies=[Depends(require_write_auth)],
    )
    def update_project(request: Request, project_id: str, payload: ExperimentInput) -> ProjectRecord:
        previous = repository.get_project(project_id, include_archived=True)
        project = repository.update_project(project_id, payload.model_dump())
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        repository.log_audit_entry(
            action="project.update",
            project_id=project["id"],
            project_name=project["project_name"],
            key_id=getattr(request.state, "auth_key_id", None),
            actor=_resolve_audit_actor(request),
            request_id=getattr(request.state, "request_id", None),
            ip_address=_request_ip(request),
            payload_diff=repository.build_payload_diff(
                previous["payload"] if previous else {},
                payload.model_dump(),
            ),
        )
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
    def record_project_analysis(request: Request, project_id: str, payload: AnalysisResponse) -> ProjectRecord:
        project = repository.record_analysis(project_id, payload.model_dump())
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        repository.log_audit_entry(
            action="analysis_run_created",
            project_id=project["id"],
            project_name=project["project_name"],
            key_id=getattr(request.state, "auth_key_id", None),
            actor=_resolve_audit_actor(request),
            request_id=getattr(request.state, "request_id", None),
            ip_address=_request_ip(request),
        )
        return ProjectRecord.model_validate(project)

    @router.post(
        "/api/v1/projects/{project_id}/exports",
        response_model=ProjectRecord,
        dependencies=[Depends(require_write_auth)],
    )
    def record_project_export(request: Request, project_id: str, payload: ProjectExportMarkRequest) -> ProjectRecord:
        project = repository.record_export(project_id, payload.format, payload.analysis_run_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        repository.log_audit_entry(
            action="export_created",
            project_id=project["id"],
            project_name=project["project_name"],
            key_id=getattr(request.state, "auth_key_id", None),
            actor=_resolve_audit_actor(request),
            request_id=getattr(request.state, "request_id", None),
            ip_address=_request_ip(request),
        )
        return ProjectRecord.model_validate(project)

    @router.post(
        "/api/v1/projects/{project_id}/archive",
        response_model=ProjectArchiveResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def archive_project(request: Request, project_id: str) -> ProjectArchiveResponse:
        project = repository.get_project(project_id, include_archived=True)
        archived = repository.archive_project(project_id)
        if not archived:
            raise HTTPException(status_code=404, detail="Project not found")
        repository.log_audit_entry(
            action="project.archive",
            project_id=project_id,
            project_name=project["project_name"] if project else None,
            key_id=getattr(request.state, "auth_key_id", None),
            actor=_resolve_audit_actor(request),
            request_id=getattr(request.state, "request_id", None),
            ip_address=_request_ip(request),
        )
        return ProjectArchiveResponse.model_validate(archived)

    @router.delete(
        "/api/v1/projects/{project_id}",
        response_model=ProjectDeleteResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def delete_project(request: Request, project_id: str) -> ProjectDeleteResponse:
        project = repository.get_project(project_id, include_archived=True)
        deleted = repository.delete_project(project_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Project not found")
        repository.log_audit_entry(
            action="project.delete",
            project_id=project_id,
            project_name=project["project_name"] if project else None,
            key_id=getattr(request.state, "auth_key_id", None),
            actor=_resolve_audit_actor(request),
            request_id=getattr(request.state, "request_id", None),
            ip_address=_request_ip(request),
        )
        return ProjectDeleteResponse.model_validate(deleted)

    @router.post(
        "/api/v1/projects/{project_id}/restore",
        response_model=ProjectRecord,
        dependencies=[Depends(require_write_auth)],
    )
    def restore_project(request: Request, project_id: str) -> ProjectRecord:
        project = repository.restore_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        repository.log_audit_entry(
            action="project.restore",
            project_id=project["id"],
            project_name=project["project_name"],
            key_id=getattr(request.state, "auth_key_id", None),
            actor=_resolve_audit_actor(request),
            request_id=getattr(request.state, "request_id", None),
            ip_address=_request_ip(request),
        )
        return ProjectRecord.model_validate(project)

    return router
