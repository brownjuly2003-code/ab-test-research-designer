import re

from fastapi import APIRouter, Depends, Response

from app.backend.app.schemas.api import ExperimentReport, ExportResponse, StandaloneExportRequest
from app.backend.app.services.export_service import (
    build_standalone_html,
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
