import base64
import re

from fastapi import APIRouter, Depends, HTTPException, Response

from app.backend.app.schemas.api import ComparisonExportRequest, ExperimentReport, ExportResponse, StandaloneExportRequest
from app.backend.app.services.comparison_service import build_multi_project_comparison
from app.backend.app.services.export_service import (
    build_standalone_html,
    export_multi_project_comparison_to_markdown,
    export_multi_project_comparison_to_pdf,
    export_report_to_html,
    export_report_to_markdown,
)


def _sanitize_filename(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*]+', "-", value).strip().strip(".")
    return sanitized or "ab-test-report"


def create_export_router(settings, repository, rate_limiter, require_auth) -> APIRouter:
    router = APIRouter(tags=["workspace"])

    @router.post(
        "/api/v1/export/markdown",
        response_model=ExportResponse,
        dependencies=[Depends(require_auth)],
    )
    def export_markdown(payload: ExperimentReport) -> ExportResponse:
        return ExportResponse(content=export_report_to_markdown(payload.model_dump()))

    @router.post(
        "/api/v1/export/html",
        response_model=ExportResponse,
        dependencies=[Depends(require_auth)],
    )
    def export_html(payload: ExperimentReport) -> ExportResponse:
        return ExportResponse(content=export_report_to_html(payload.model_dump()))

    @router.post(
        "/api/v1/export/comparison",
        response_model=ExportResponse,
        dependencies=[Depends(require_auth)],
    )
    def export_comparison(payload: ComparisonExportRequest) -> ExportResponse:
        projects_with_runs: list[tuple[dict, dict]] = []
        for project_id in payload.project_ids:
            project = repository.get_project(project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="Project not found")
            analysis_run = repository.get_latest_analysis_run(project_id)
            if analysis_run is None:
                raise HTTPException(status_code=404, detail="Project analysis snapshot not found")
            projects_with_runs.append((project, analysis_run))

        comparison = build_multi_project_comparison(projects_with_runs)
        if payload.format == "markdown":
            return ExportResponse(content=export_multi_project_comparison_to_markdown(comparison))
        return ExportResponse(
            content=base64.b64encode(export_multi_project_comparison_to_pdf(comparison)).decode("ascii")
        )

    @router.post(
        "/api/v1/export/html-standalone",
        dependencies=[Depends(require_auth)],
    )
    def export_html_standalone(payload: StandaloneExportRequest) -> Response:
        filename = f'{_sanitize_filename(payload.project_name)}-report.html'
        return Response(
            content=build_standalone_html(payload),
            media_type="text/html",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return router
