from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.backend.app.config import get_settings
from app.backend.app.llm.adapter import LocalOrchestratorAdapter
from app.backend.app.repository import ProjectRepository
from app.backend.app.services.calculations_service import calculate_experiment_metrics
from app.backend.app.services.design_service import build_experiment_report
from app.backend.app.services.export_service import export_report_to_html, export_report_to_markdown


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


def _build_calculation_payload(payload: dict) -> dict:
    return {
        "metric_type": payload["metrics"]["metric_type"],
        "baseline_value": payload["metrics"]["baseline_value"],
        "std_dev": payload["metrics"].get("std_dev"),
        "mde_pct": payload["metrics"]["mde_pct"],
        "alpha": payload["metrics"]["alpha"],
        "power": payload["metrics"]["power"],
        "expected_daily_traffic": payload["setup"]["expected_daily_traffic"],
        "audience_share_in_test": payload["setup"]["audience_share_in_test"],
        "traffic_split": payload["setup"]["traffic_split"],
        "variants_count": payload["setup"]["variants_count"],
        "seasonality_present": payload.get("constraints", {}).get("seasonality_present"),
        "active_campaigns_present": payload.get("constraints", {}).get("active_campaigns_present"),
        "long_test_possible": payload.get("constraints", {}).get("long_test_possible"),
    }


def create_app() -> FastAPI:
    settings = get_settings()
    llm_adapter = LocalOrchestratorAdapter()
    repository = ProjectRepository(settings.db_path)

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

    @app.post("/api/v1/calculate")
    def calculate(payload: dict) -> dict:
        try:
            return calculate_experiment_metrics(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/v1/design")
    def design(payload: dict) -> dict:
        try:
            calculation_payload = _build_calculation_payload(payload)
            calculation_result = calculate_experiment_metrics(calculation_payload)
            return build_experiment_report(payload, calculation_result)
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/v1/llm/advice")
    def llm_advice(payload: dict) -> dict:
        try:
            return llm_adapter.request_advice(payload)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/v1/projects")
    def list_projects() -> dict:
        return {"projects": repository.list_projects()}

    @app.post("/api/v1/projects")
    def create_project(payload: dict) -> dict:
        try:
            return repository.create_project(payload)
        except (KeyError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/v1/projects/{project_id}")
    def get_project(project_id: str) -> dict:
        project = repository.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return project

    @app.put("/api/v1/projects/{project_id}")
    def update_project(project_id: str, payload: dict) -> dict:
        try:
            project = repository.update_project(project_id, payload)
        except (KeyError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return project

    @app.post("/api/v1/export/markdown")
    def export_markdown(payload: dict) -> dict:
        try:
            return {"content": export_report_to_markdown(payload)}
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/v1/export/html")
    def export_html(payload: dict) -> dict:
        try:
            return {"content": export_report_to_html(payload)}
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


app = create_app()
