from fastapi import APIRouter, Depends

from app.backend.app.schemas.api import WorkspaceBundle, WorkspaceImportResponse, WorkspaceValidationResponse


def create_workspace_router(settings, repository, rate_limiter, require_auth, require_write_auth) -> APIRouter:
    router = APIRouter(tags=["workspace"])

    @router.get(
        "/api/v1/workspace/export",
        response_model=WorkspaceBundle,
        dependencies=[Depends(require_auth)],
    )
    def export_workspace() -> WorkspaceBundle:
        return WorkspaceBundle.model_validate(repository.export_workspace())

    @router.post(
        "/api/v1/workspace/validate",
        response_model=WorkspaceValidationResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def validate_workspace(payload: WorkspaceBundle) -> WorkspaceValidationResponse:
        return WorkspaceValidationResponse.model_validate(repository.validate_workspace_bundle(payload.model_dump()))

    @router.post(
        "/api/v1/workspace/import",
        response_model=WorkspaceImportResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def import_workspace(payload: WorkspaceBundle) -> WorkspaceImportResponse:
        return WorkspaceImportResponse.model_validate(repository.import_workspace(payload.model_dump()))

    return router
