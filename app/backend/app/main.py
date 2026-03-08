from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from pathlib import Path
from time import perf_counter
import uuid

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.backend.app.config import get_settings
from app.backend.app.errors import ApiError
from app.backend.app.llm.adapter import LocalOrchestratorAdapter
from app.backend.app.logging_utils import configure_logging, log_event
from app.backend.app.repository import ProjectRepository
from app.backend.app.schemas.api import (
    AnalysisResponse,
    CalculationRequest,
    CalculationResponse,
    DiagnosticsResponse,
    ErrorResponse,
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
    WorkspaceValidationResponse,
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


AUTH_EXEMPT_PREFIXES = ("/assets",)
AUTH_PROTECTED_EXACT_PATHS = {"/readyz", "/docs", "/openapi.json", "/redoc"}
AUTH_READ_ONLY_METHODS = {"GET", "HEAD", "OPTIONS"}


def _is_protected_path(path: str) -> bool:
    if path.startswith("/api/v1"):
        return True
    if path in AUTH_PROTECTED_EXACT_PATHS:
        return True
    if any(path.startswith(prefix) for prefix in AUTH_EXEMPT_PREFIXES):
        return False
    return False


def _extract_presented_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        return token or None
    api_key = request.headers.get("x-api-key", "").strip()
    return api_key or None


def _get_auth_mode(write_token: str | None, readonly_token: str | None) -> str:
    if write_token and readonly_token:
        return "dual_token"
    if write_token:
        return "token"
    if readonly_token:
        return "readonly"
    return "open"


def _get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


def _get_process_time_ms(request: Request) -> float:
    started = getattr(request.state, "request_started", None)
    if started is None:
        return 0.0
    return (perf_counter() - started) * 1000


def _build_error_response(
    request: Request,
    *,
    detail: str | list[dict] | dict,
    error_code: str,
    status_code: int,
    extra_headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = _get_request_id(request)
    process_time_ms = _get_process_time_ms(request)
    response = JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            detail=detail,
            error_code=error_code,
            status_code=status_code,
            request_id=request_id,
        ).model_dump(),
        headers=extra_headers or {},
    )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = f"{process_time_ms:.2f}"
    response.headers["X-Error-Code"] = error_code
    return response


def _build_auth_failure_response(request: Request, detail: str, status_code: int, error_code: str) -> JSONResponse:
    extra_headers = {"WWW-Authenticate": "Bearer"} if status_code == status.HTTP_401_UNAUTHORIZED else None
    return _build_error_response(
        request,
        detail=detail,
        error_code=error_code,
        status_code=status_code,
        extra_headers=extra_headers,
    )


def _get_http_error_code(status_code: int) -> str:
    if status_code == status.HTTP_401_UNAUTHORIZED:
        return "unauthorized"
    if status_code == status.HTTP_403_FORBIDDEN:
        return "forbidden"
    if status_code == status.HTTP_404_NOT_FOUND:
        return "not_found"
    return "http_error"


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
    configure_logging(level=settings.log_level, log_format=settings.log_format)
    started_at = datetime.now(timezone.utc)
    llm_adapter = LocalOrchestratorAdapter(
        base_url=settings.llm_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        max_attempts=settings.llm_max_attempts,
        initial_backoff_seconds=settings.llm_initial_backoff_seconds,
        backoff_multiplier=settings.llm_backoff_multiplier,
    )
    repository = ProjectRepository(
        settings.db_path,
        busy_timeout_ms=settings.sqlite_busy_timeout_ms,
        journal_mode=settings.sqlite_journal_mode,
        synchronous=settings.sqlite_synchronous,
    )
    frontend_dist_path = Path(settings.frontend_dist_path)
    frontend_index_path = frontend_dist_path / "index.html"
    runtime_counters = {
        "total_requests": 0,
        "success_responses": 0,
        "client_error_responses": 0,
        "server_error_responses": 0,
        "auth_rejections": 0,
        "last_request_at": None,
        "last_error_at": None,
        "last_error_code": None,
    }
    cors_headers = list(settings.cors_headers)
    if settings.api_token or settings.readonly_api_token:
        for header_name in ("Authorization", "X-API-Key"):
            if header_name not in cors_headers:
                cors_headers.append(header_name)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        log_event(
            logger,
            logging.INFO,
            "application started",
            event="startup",
            environment=settings.environment,
            version=settings.app_version,
            db_path=settings.db_path,
            sqlite_journal_mode=settings.sqlite_journal_mode,
            sqlite_synchronous=settings.sqlite_synchronous,
            log_format=settings.log_format,
            auth_mode=_get_auth_mode(settings.api_token, settings.readonly_api_token),
        )
        yield

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Local backend for A/B experiment planning.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=list(settings.cors_methods),
        allow_headers=cors_headers,
    )

    def record_runtime_response(status_code: int, error_code: str | None = None, *, auth_rejection: bool = False) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        runtime_counters["total_requests"] += 1
        runtime_counters["last_request_at"] = timestamp
        if status_code >= 500:
            runtime_counters["server_error_responses"] += 1
        elif status_code >= 400:
            runtime_counters["client_error_responses"] += 1
        else:
            runtime_counters["success_responses"] += 1

        if auth_rejection:
            runtime_counters["auth_rejections"] += 1

        if error_code:
            runtime_counters["last_error_at"] = timestamp
            runtime_counters["last_error_code"] = error_code

    @app.middleware("http")
    async def add_request_metadata(request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        started = perf_counter()
        request.state.request_id = request_id
        request.state.request_started = started

        if (
            (settings.api_token or settings.readonly_api_token)
            and request.method != "OPTIONS"
            and _is_protected_path(request.url.path)
        ):
            presented_token = _extract_presented_token(request)

            if settings.api_token and presented_token == settings.api_token:
                pass
            elif settings.readonly_api_token and presented_token == settings.readonly_api_token:
                if request.method not in AUTH_READ_ONLY_METHODS:
                    response = _build_auth_failure_response(
                        request,
                        "Forbidden",
                        status.HTTP_403_FORBIDDEN,
                        "forbidden",
                    )
                    log_event(
                        logger,
                        logging.WARNING,
                        "request rejected",
                        event="http_request_auth",
                        request_id=request_id,
                        method=request.method,
                        path=request.url.path,
                        status_code=response.status_code,
                        process_time_ms=round(_get_process_time_ms(request), 2),
                        auth_mode=_get_auth_mode(settings.api_token, settings.readonly_api_token),
                        auth_scope="readonly",
                        error_code="forbidden",
                    )
                    record_runtime_response(response.status_code, "forbidden", auth_rejection=True)
                    return response
            else:
                response = _build_auth_failure_response(
                    request,
                    "Unauthorized",
                    status.HTTP_401_UNAUTHORIZED,
                    "unauthorized",
                )
                log_event(
                    logger,
                    logging.WARNING,
                    "request rejected",
                    event="http_request_auth",
                    request_id=request_id,
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    process_time_ms=round(_get_process_time_ms(request), 2),
                    auth_mode=_get_auth_mode(settings.api_token, settings.readonly_api_token),
                    error_code="unauthorized",
                )
                record_runtime_response(response.status_code, "unauthorized", auth_rejection=True)
                return response

        try:
            response = await call_next(request)
        except Exception:
            log_event(
                logger,
                logging.ERROR,
                "request failed",
                event="http_request",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                process_time_ms=round(_get_process_time_ms(request), 2),
            )
            raise

        process_time_ms = (perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{process_time_ms:.2f}"
        record_runtime_response(
            response.status_code,
            response.headers.get("X-Error-Code"),
        )
        log_event(
            logger,
            logging.INFO,
            "request completed",
            event="http_request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            process_time_ms=round(process_time_ms, 2),
        )
        return response

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        log_event(
            logger,
            logging.WARNING if exc.status_code < 500 else logging.ERROR,
            "api error handled",
            event="http_request_error",
            request_id=_get_request_id(request),
            method=request.method,
            path=request.url.path,
            status_code=exc.status_code,
            error_code=exc.error_code,
            process_time_ms=round(_get_process_time_ms(request), 2),
        )
        return _build_error_response(
            request,
            detail=exc.detail,
            error_code=exc.error_code,
            status_code=exc.status_code,
        )

    @app.exception_handler(ValueError)
    async def handle_value_error(request: Request, exc: ValueError) -> JSONResponse:
        log_event(
            logger,
            logging.WARNING,
            "value error handled",
            event="http_request_error",
            request_id=_get_request_id(request),
            method=request.method,
            path=request.url.path,
            status_code=400,
            error_code="bad_request",
            process_time_ms=round(_get_process_time_ms(request), 2),
        )
        return _build_error_response(
            request,
            detail=str(exc),
            error_code="bad_request",
            status_code=400,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _build_error_response(
            request,
            detail=jsonable_encoder(exc.errors()),
            error_code="validation_error",
            status_code=422,
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        error_code = _get_http_error_code(exc.status_code)
        return _build_error_response(
            request,
            detail=exc.detail,
            error_code=error_code,
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled exception while serving %s %s",
            request.method,
            request.url.path,
            exc_info=exc,
        )
        return _build_error_response(
            request,
            detail="Internal server error",
            error_code="internal_error",
            status_code=500,
        )

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
            checks.append(
                ReadinessCheck(
                    name="sqlite_schema_version",
                    ok=storage_summary["sqlite_user_version"] == repository.schema_version,
                    detail=(
                        f"user_version={storage_summary['sqlite_user_version']} expected={repository.schema_version}"
                    ),
                )
            )
            checks.append(
                ReadinessCheck(
                    name="sqlite_journal_mode",
                    ok=storage_summary["journal_mode"] == settings.sqlite_journal_mode,
                    detail=(
                        f"journal_mode={storage_summary['journal_mode']} expected={settings.sqlite_journal_mode}"
                    ),
                )
            )
            checks.append(
                ReadinessCheck(
                    name="sqlite_write_probe",
                    ok=storage_summary["write_probe_ok"],
                    detail=storage_summary["write_probe_detail"],
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
        checks.append(
            ReadinessCheck(
                name="logging_config",
                ok=True,
                detail=f"{settings.log_level} / {settings.log_format}",
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
            logging={
                "level": settings.log_level,
                "format": settings.log_format,
            },
            auth={
                "enabled": settings.api_token is not None or settings.readonly_api_token is not None,
                "mode": _get_auth_mode(settings.api_token, settings.readonly_api_token),
                "write_enabled": settings.api_token is not None,
                "readonly_enabled": settings.readonly_api_token is not None,
                "accepted_headers": ["Authorization: Bearer", "X-API-Key"],
                "read_only_methods": sorted(AUTH_READ_ONLY_METHODS),
            },
            runtime=runtime_counters,
        )

    @app.get("/api/v1/workspace/export", response_model=WorkspaceBundle)
    def export_workspace() -> WorkspaceBundle:
        return WorkspaceBundle.model_validate(repository.export_workspace())

    @app.post("/api/v1/workspace/validate", response_model=WorkspaceValidationResponse)
    def validate_workspace(payload: WorkspaceBundle) -> WorkspaceValidationResponse:
        return WorkspaceValidationResponse.model_validate(repository.validate_workspace_bundle(payload.model_dump()))

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
