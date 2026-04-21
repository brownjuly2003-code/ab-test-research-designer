from fastapi import APIRouter, Depends, Query, Response

from app.backend.app.schemas.api import AuditLogResponse


def create_audit_router(settings, repository, rate_limiter, require_auth, require_write_auth) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/v1/audit",
        response_model=AuditLogResponse,
        dependencies=[Depends(require_auth)],
    )
    def get_audit_log(
        project_id: str | None = Query(default=None),
        action: str | None = Query(default=None),
        limit: int = Query(default=500, ge=1, le=500),
    ) -> AuditLogResponse:
        return AuditLogResponse.model_validate(
            repository.list_audit_entries(project_id=project_id, action=action, limit=limit)
        )

    @router.get(
        "/api/v1/audit/export",
        dependencies=[Depends(require_write_auth)],
    )
    def export_audit_log(
        project_id: str | None = Query(default=None),
        action: str | None = Query(default=None),
    ) -> Response:
        content = repository.export_audit_entries_csv(project_id=project_id, action=action)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="audit-log.csv"'},
        )

    return router
