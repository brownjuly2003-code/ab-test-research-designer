from datetime import datetime, timezone
import logging
from pathlib import Path
from time import perf_counter
import uuid

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.backend.app.config import get_settings
from app.backend.app.llm.adapter import LocalOrchestratorAdapter
from app.backend.app.repository import ProjectRepository
from app.backend.app.schemas.api import (
    AnalysisResponse,
    CalculationRequest,
    CalculationResponse,
    DiagnosticsResponse,
    ExperimentInput,
    ExperimentReport,
    ExportResponse,
    LlmAdviceRequest,
    LlmAdviceResponse,
    ProjectComparisonResponse,
    ProjectDeleteResponse,
    ProjectExportMarkRequest,
    ProjectHistoryResponse,
    ProjectListResponse,
    ProjectRecord,
    ProjectRevisionHistoryResponse,
    ReadinessCheck,
    ReadinessResponse,
    WorkspaceBundle,
    WorkspaceImportResponse,
)
from app.backend.app.services.calculations_service import calculate_experiment_metrics
from app.backend.app.services.comparison_service import build_project_comparison
from app.backend.app.services.design_service import build_experiment_report
from app.backend.app.services.export_service import export_report_to_html, export_report_to_markdown

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


def _build_calculation_payload(payload: ExperimentInput) -> CalculationRequest:
    return CalculationRequest(
        metric_type=payload.metrics.metric_type,
        baseline_value=payload.metrics.baseline_value,
        std_dev=payload.metrics.std_dev,
        mde_pct=payload.metrics.mde_pct,
        alpha=payload.metrics.alpha,
        power=payload.metrics.power,
        expected_daily_traffic=payload.setup.expected_daily_traffic,
        audience_share_in_test=payload.setup.audience_share_in_test,
        traffic_split=payload.setup.traffic_split,
        variants_count=payload.setup.variants_count,
        seasonality_present=payload.constraints.seasonality_present,
        active_campaigns_present=payload.constraints.active_campaigns_present,
        long_test_possible=payload.constraints.long_test_possible,
    )


def _build_llm_advice_payload(payload: ExperimentInput, calculation_result: dict) -> dict:
    normalized_payload = payload.model_dump()
    return {
        "project_context": normalized_payload["project"],
        "hypothesis": normalized_payload["hypothesis"],
        "setup": normalized_payload["setup"],
        "metrics": normalized_payload["metrics"],
        "constraints": normalized_payload["constraints"],
        "additional_context": normalized_payload["additional_context"],
        "calculation_results": calculation_result["results"],
        "warnings": calculation_result.get("warnings", []),
    }


def create_app() -> FastAPI:
    settings = get_settings()
    started_at = datetime.now(timezone.utc)
    llm_adapter = LocalOrchestratorAdapter(
        base_url=settings.llm_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        max_attempts=settings.llm_max_attempts,
        initial_backoff_seconds=settings.llm_initial_backoff_seconds,
        backoff_multiplier=settings.llm_backoff_multiplier,
    )
    repository = ProjectRepository(settings.db_path)
    frontend_dist_path = Path(settings.frontend_dist_path)
    frontend_index_path = frontend_dist_path / "index.html"

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Local backend for A/B experiment planning.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=list(settings.cors_methods),
        allow_headers=list(settings.cors_headers),
    )

    @app.middleware("http")
    async def add_request_metadata(request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        started = perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{(perf_counter() - started) * 1000:.2f}"
        return response

    @app.exception_handler(ValueError)
    async def handle_value_error(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled exception while serving %s %s",
            request.method,
            request.url.path,
            exc_info=exc,
        )
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=settings.app_name,
            version=settings.app_version,
            environment=settings.environment,
        )

    @app.get("/readyz", response_model=ReadinessResponse)
    def readyz(response: Response) -> ReadinessResponse:
        checks: list[ReadinessCheck] = []

        try:
            storage_summary = repository.get_diagnostics_summary()
            checks.append(
                ReadinessCheck(
                    name="sqlite_storage",
                    ok=True,
                    detail=f"Database path {storage_summary['db_path']}",
                )
            )
        except Exception as exc:  # pragma: no cover - exercised via endpoint tests
            checks.append(
                ReadinessCheck(
                    name="sqlite_storage",
                    ok=False,
                    detail=f"Storage diagnostics failed: {exc}",
                )
            )

        frontend_ready = (not settings.serve_frontend_dist) or frontend_index_path.exists()
        checks.append(
            ReadinessCheck(
                name="frontend_dist",
                ok=frontend_ready,
                detail=(
                    "Frontend dist serving disabled"
                    if not settings.serve_frontend_dist
                    else f"Looking for {frontend_index_path}"
                ),
            )
        )
        checks.append(
            ReadinessCheck(
                name="llm_config",
                ok=True,
                detail=f"{settings.llm_max_attempts} attempt(s), timeout {settings.llm_timeout_seconds}s",
            )
        )

        ready = all(check.ok for check in checks)
        response.status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            status="ready" if ready else "degraded",
            generated_at=datetime.now(timezone.utc).isoformat(),
            checks=checks,
        )

    @app.get("/api/v1/diagnostics", response_model=DiagnosticsResponse)
    def diagnostics() -> DiagnosticsResponse:
        diagnostics_generated_at = datetime.now(timezone.utc)
        storage_summary = repository.get_diagnostics_summary()

        return DiagnosticsResponse(
            status="ok",
            generated_at=diagnostics_generated_at.isoformat(),
            started_at=started_at.isoformat(),
            uptime_seconds=round((diagnostics_generated_at - started_at).total_seconds(), 3),
            environment=settings.environment,
            app_version=settings.app_version,
            request_timing_headers_enabled=True,
            storage=storage_summary,
            frontend={
                "serve_frontend_dist": settings.serve_frontend_dist,
                "dist_path": settings.frontend_dist_path,
                "dist_exists": frontend_dist_path.exists(),
            },
            llm={
                "provider": "local_orchestrator",
                "base_url": settings.llm_base_url,
                "timeout_seconds": settings.llm_timeout_seconds,
                "max_attempts": settings.llm_max_attempts,
                "initial_backoff_seconds": settings.llm_initial_backoff_seconds,
                "backoff_multiplier": settings.llm_backoff_multiplier,
            },
        )

    @app.get("/api/v1/workspace/export", response_model=WorkspaceBundle)
    def export_workspace() -> WorkspaceBundle:
        return WorkspaceBundle.model_validate(repository.export_workspace())

    @app.post("/api/v1/workspace/import", response_model=WorkspaceImportResponse)
    def import_workspace(payload: WorkspaceBundle) -> WorkspaceImportResponse:
        return WorkspaceImportResponse.model_validate(repository.import_workspace(payload.model_dump()))

    @app.post("/api/v1/calculate", response_model=CalculationResponse)
    def calculate(payload: CalculationRequest) -> CalculationResponse:
        result = calculate_experiment_metrics(payload.model_dump())
        return CalculationResponse.model_validate(result)

    @app.post("/api/v1/design", response_model=ExperimentReport)
    def design(payload: ExperimentInput) -> ExperimentReport:
        calculation_payload = _build_calculation_payload(payload)
        calculation_result = calculate_experiment_metrics(calculation_payload.model_dump())
        report = build_experiment_report(payload.model_dump(), calculation_result)
        return ExperimentReport.model_validate(report)

    @app.post("/api/v1/analyze", response_model=AnalysisResponse)
    def analyze(payload: ExperimentInput) -> AnalysisResponse:
        calculation_payload = _build_calculation_payload(payload)
        calculation_result = calculate_experiment_metrics(calculation_payload.model_dump())
        report = build_experiment_report(payload.model_dump(), calculation_result)
        advice = llm_adapter.request_advice(_build_llm_advice_payload(payload, calculation_result))
        return AnalysisResponse(
            calculations=CalculationResponse.model_validate(calculation_result),
            report=ExperimentReport.model_validate(report),
            advice=LlmAdviceResponse.model_validate(advice),
        )

    @app.post("/api/v1/llm/advice", response_model=LlmAdviceResponse)
    def llm_advice(payload: LlmAdviceRequest) -> LlmAdviceResponse:
        result = llm_adapter.request_advice(payload.model_dump(exclude_none=True))
        return LlmAdviceResponse.model_validate(result)

    @app.get("/api/v1/projects", response_model=ProjectListResponse)
    def list_projects() -> ProjectListResponse:
        return ProjectListResponse.model_validate({"projects": repository.list_projects()})

    @app.post("/api/v1/projects", response_model=ProjectRecord)
    def create_project(payload: ExperimentInput) -> ProjectRecord:
        project = repository.create_project(payload.model_dump())
        return ProjectRecord.model_validate(project)

    @app.get("/api/v1/projects/compare", response_model=ProjectComparisonResponse)
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

    @app.get("/api/v1/projects/{project_id}", response_model=ProjectRecord)
    def get_project(project_id: str) -> ProjectRecord:
        project = repository.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectRecord.model_validate(project)

    @app.put("/api/v1/projects/{project_id}", response_model=ProjectRecord)
    def update_project(project_id: str, payload: ExperimentInput) -> ProjectRecord:
        project = repository.update_project(project_id, payload.model_dump())
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectRecord.model_validate(project)

    @app.get("/api/v1/projects/{project_id}/history", response_model=ProjectHistoryResponse)
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

    @app.get("/api/v1/projects/{project_id}/revisions", response_model=ProjectRevisionHistoryResponse)
    def get_project_revisions(
        project_id: str,
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> ProjectRevisionHistoryResponse:
        revisions = repository.get_project_revisions(project_id, limit=limit, offset=offset)
        if revisions is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectRevisionHistoryResponse.model_validate(revisions)

    @app.post("/api/v1/projects/{project_id}/analysis", response_model=ProjectRecord)
    def record_project_analysis(project_id: str, payload: AnalysisResponse) -> ProjectRecord:
        project = repository.record_analysis(project_id, payload.model_dump())
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectRecord.model_validate(project)

    @app.post("/api/v1/projects/{project_id}/exports", response_model=ProjectRecord)
    def record_project_export(project_id: str, payload: ProjectExportMarkRequest) -> ProjectRecord:
        project = repository.record_export(project_id, payload.format, payload.analysis_run_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectRecord.model_validate(project)

    @app.delete("/api/v1/projects/{project_id}", response_model=ProjectDeleteResponse)
    def delete_project(project_id: str) -> ProjectDeleteResponse:
        deleted = repository.delete_project(project_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectDeleteResponse(id=project_id, deleted=True)

    @app.post("/api/v1/export/markdown", response_model=ExportResponse)
    def export_markdown(payload: ExperimentReport) -> ExportResponse:
        return ExportResponse(content=export_report_to_markdown(payload.model_dump()))

    @app.post("/api/v1/export/html", response_model=ExportResponse)
    def export_html(payload: ExperimentReport) -> ExportResponse:
        return ExportResponse(content=export_report_to_html(payload.model_dump()))

    if settings.serve_frontend_dist and frontend_index_path.exists():
        assets_path = frontend_dist_path / "assets"

        if assets_path.exists():
            app.mount("/assets", StaticFiles(directory=assets_path), name="frontend-assets")

        @app.get("/", include_in_schema=False)
        def serve_frontend_index() -> FileResponse:
            return FileResponse(frontend_index_path)

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_frontend_app(full_path: str) -> FileResponse:
            if full_path.startswith(("api/", "health", "docs", "openapi.json", "redoc")):
                raise HTTPException(status_code=404, detail="Not found")

            candidate = frontend_dist_path / full_path
            if candidate.is_file():
                return FileResponse(candidate)

            return FileResponse(frontend_index_path)

    return app


app = create_app()
