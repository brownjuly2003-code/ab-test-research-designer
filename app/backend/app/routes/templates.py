from fastapi import APIRouter, Depends, HTTPException

from app.backend.app.schemas.template import (
    TemplateCreateRequest,
    TemplateDeleteResponse,
    TemplateListResponse,
    TemplateRecord,
)
from app.backend.app.services.template_service import sync_built_in_templates


def create_templates_router(settings, repository, rate_limiter, require_auth, require_write_auth) -> APIRouter:
    router = APIRouter()

    def ensure_templates_seeded() -> None:
        sync_built_in_templates(repository)

    @router.get(
        "/api/v1/templates",
        response_model=TemplateListResponse,
        dependencies=[Depends(require_auth)],
    )
    def list_templates() -> TemplateListResponse:
        ensure_templates_seeded()
        templates = repository.list_templates()
        return TemplateListResponse.model_validate(
            {
                "templates": templates,
                "total": len(templates),
            }
        )

    @router.get(
        "/api/v1/templates/{template_id}",
        response_model=TemplateRecord,
        dependencies=[Depends(require_auth)],
    )
    def get_template(template_id: str) -> TemplateRecord:
        ensure_templates_seeded()
        template = repository.get_template(template_id)
        if template is None:
            raise HTTPException(status_code=404, detail="Template not found")
        return TemplateRecord.model_validate(template)

    @router.post(
        "/api/v1/templates",
        response_model=TemplateRecord,
        dependencies=[Depends(require_write_auth)],
    )
    def create_template(payload: TemplateCreateRequest) -> TemplateRecord:
        ensure_templates_seeded()
        return TemplateRecord.model_validate(
            repository.create_template(
                name=payload.name,
                category=payload.category,
                description=payload.description,
                tags=payload.tags,
                payload=payload.payload.model_dump(),
            )
        )

    @router.post(
        "/api/v1/templates/{template_id}/use",
        response_model=TemplateRecord,
        dependencies=[Depends(require_write_auth)],
    )
    def use_template(template_id: str) -> TemplateRecord:
        ensure_templates_seeded()
        template = repository.use_template(template_id)
        if template is None:
            raise HTTPException(status_code=404, detail="Template not found")
        return TemplateRecord.model_validate(template)

    @router.delete(
        "/api/v1/templates/{template_id}",
        response_model=TemplateDeleteResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def delete_template(template_id: str) -> TemplateDeleteResponse:
        ensure_templates_seeded()
        deleted = repository.delete_template(template_id)
        if deleted is None:
            raise HTTPException(status_code=404, detail="Template not found")
        return TemplateDeleteResponse.model_validate(deleted)

    return router
