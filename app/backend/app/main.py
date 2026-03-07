from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.backend.app.config import get_settings
from app.backend.app.llm.adapter import LocalOrchestratorAdapter
from app.backend.app.repository import ProjectRepository
from app.backend.app.schemas.api import (
    AnalysisResponse,
    CalculationRequest,
    CalculationResponse,
    ExperimentInput,
    ExperimentReport,
    ExportResponse,
    LlmAdviceRequest,
    LlmAdviceResponse,
    ProjectDeleteResponse,
    ProjectListResponse,
    ProjectRecord,
)
from app.backend.app.services.calculations_service import calculate_experiment_metrics
from app.backend.app.services.design_service import build_experiment_report
from app.backend.app.services.export_service import export_report_to_html, export_report_to_markdown


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
    llm_adapter = LocalOrchestratorAdapter()
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
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=settings.app_name,
            version=settings.app_version,
            environment=settings.environment,
        )

    @app.post("/api/v1/calculate", response_model=CalculationResponse)
    def calculate(payload: CalculationRequest) -> CalculationResponse:
        try:
            result = calculate_experiment_metrics(payload.model_dump())
            return CalculationResponse.model_validate(result)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/v1/design", response_model=ExperimentReport)
    def design(payload: ExperimentInput) -> ExperimentReport:
        try:
            calculation_payload = _build_calculation_payload(payload)
            calculation_result = calculate_experiment_metrics(calculation_payload.model_dump())
            report = build_experiment_report(payload.model_dump(), calculation_result)
            return ExperimentReport.model_validate(report)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/v1/analyze", response_model=AnalysisResponse)
    def analyze(payload: ExperimentInput) -> AnalysisResponse:
        try:
            calculation_payload = _build_calculation_payload(payload)
            calculation_result = calculate_experiment_metrics(calculation_payload.model_dump())
            report = build_experiment_report(payload.model_dump(), calculation_result)
            advice = llm_adapter.request_advice(_build_llm_advice_payload(payload, calculation_result))
            return AnalysisResponse(
                calculations=CalculationResponse.model_validate(calculation_result),
                report=ExperimentReport.model_validate(report),
                advice=LlmAdviceResponse.model_validate(advice),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/v1/llm/advice", response_model=LlmAdviceResponse)
    def llm_advice(payload: LlmAdviceRequest) -> LlmAdviceResponse:
        try:
            result = llm_adapter.request_advice(payload.model_dump(exclude_none=True))
            return LlmAdviceResponse.model_validate(result)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/v1/projects", response_model=ProjectListResponse)
    def list_projects() -> ProjectListResponse:
        return ProjectListResponse.model_validate({"projects": repository.list_projects()})

    @app.post("/api/v1/projects", response_model=ProjectRecord)
    def create_project(payload: ExperimentInput) -> ProjectRecord:
        project = repository.create_project(payload.model_dump())
        return ProjectRecord.model_validate(project)

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
