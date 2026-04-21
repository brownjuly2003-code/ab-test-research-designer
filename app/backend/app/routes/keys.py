from fastapi import APIRouter, Depends, HTTPException, Request

from app.backend.app.schemas.api import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyDeleteResponse,
    ApiKeyListResponse,
    ApiKeyRecord,
)


def _request_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def create_keys_router(settings, repository, require_admin_auth) -> APIRouter:
    router = APIRouter(tags=["keys"])

    @router.post(
        "/api/v1/keys",
        response_model=ApiKeyCreateResponse,
        dependencies=[Depends(require_admin_auth)],
    )
    def create_api_key(request: Request, payload: ApiKeyCreateRequest) -> ApiKeyCreateResponse:
        api_key = repository.create_api_key(
            name=payload.name,
            scope=payload.scope,
            rate_limit_requests=payload.rate_limit_requests,
            rate_limit_window_seconds=payload.rate_limit_window_seconds,
        )
        repository.log_audit_entry(
            action="api_key_created",
            key_id=api_key["id"],
            actor="admin_token",
            request_id=getattr(request.state, "request_id", None),
            ip_address=_request_ip(request),
        )
        return ApiKeyCreateResponse.model_validate(api_key)

    @router.get(
        "/api/v1/keys",
        response_model=ApiKeyListResponse,
        dependencies=[Depends(require_admin_auth)],
    )
    def list_api_keys() -> ApiKeyListResponse:
        return ApiKeyListResponse.model_validate(repository.list_api_keys())

    @router.post(
        "/api/v1/keys/{api_key_id}/revoke",
        response_model=ApiKeyRecord,
        dependencies=[Depends(require_admin_auth)],
    )
    def revoke_api_key(request: Request, api_key_id: str) -> ApiKeyRecord:
        api_key = repository.revoke_api_key(api_key_id)
        if api_key is None:
            raise HTTPException(status_code=404, detail="API key not found")
        repository.log_audit_entry(
            action="api_key_revoked",
            key_id=api_key["id"],
            actor="admin_token",
            request_id=getattr(request.state, "request_id", None),
            ip_address=_request_ip(request),
        )
        return ApiKeyRecord.model_validate(api_key)

    @router.delete(
        "/api/v1/keys/{api_key_id}",
        response_model=ApiKeyDeleteResponse,
        dependencies=[Depends(require_admin_auth)],
    )
    def delete_api_key(request: Request, api_key_id: str) -> ApiKeyDeleteResponse:
        deleted = repository.delete_api_key(api_key_id)
        if deleted is None:
            raise HTTPException(status_code=404, detail="API key not found")
        repository.log_audit_entry(
            action="api_key_deleted",
            key_id=api_key_id,
            actor="admin_token",
            request_id=getattr(request.state, "request_id", None),
            ip_address=_request_ip(request),
        )
        return ApiKeyDeleteResponse.model_validate(deleted)

    return router
