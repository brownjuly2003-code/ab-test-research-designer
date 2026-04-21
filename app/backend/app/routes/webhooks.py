from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.backend.app.schemas.api import (
    WebhookDeleteResponse,
    WebhookDeliveryListResponse,
    WebhookListResponse,
    WebhookSubscriptionCreateRequest,
    WebhookSubscriptionRecord,
    WebhookSubscriptionUpdateRequest,
    WebhookTestResponse,
)


def _request_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _validate_webhook_target_url(settings, target_url: str) -> str:
    parsed = urlparse(target_url.strip())
    if parsed.scheme == "https" and parsed.netloc:
        return target_url.strip()
    if (
        settings.environment == "local"
        and parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1"}
        and parsed.netloc
    ):
        return target_url.strip()
    raise ValueError("Webhook target_url must use HTTPS unless AB_ENV=local and host is localhost or 127.0.0.1")


def create_webhooks_router(settings, repository, require_admin_auth) -> APIRouter:
    router = APIRouter(tags=["webhooks"])

    @router.post(
        "/api/v1/webhooks",
        response_model=WebhookSubscriptionRecord,
        dependencies=[Depends(require_admin_auth)],
    )
    def create_webhook(payload: WebhookSubscriptionCreateRequest) -> WebhookSubscriptionRecord:
        subscription = repository.create_webhook_subscription(
            name=payload.name,
            target_url=_validate_webhook_target_url(settings, payload.target_url),
            secret=payload.secret,
            format=payload.format,
            event_filter=payload.event_filter,
            scope=payload.scope,
            api_key_id=payload.api_key_id,
        )
        return WebhookSubscriptionRecord.model_validate(subscription)

    @router.get(
        "/api/v1/webhooks",
        response_model=WebhookListResponse,
        dependencies=[Depends(require_admin_auth)],
    )
    def list_webhooks() -> WebhookListResponse:
        return WebhookListResponse.model_validate(repository.list_webhook_subscriptions())

    @router.get(
        "/api/v1/webhooks/{subscription_id}",
        response_model=WebhookSubscriptionRecord,
        dependencies=[Depends(require_admin_auth)],
    )
    def get_webhook(subscription_id: str) -> WebhookSubscriptionRecord:
        subscription = repository.get_webhook_subscription(subscription_id)
        if subscription is None:
            raise HTTPException(status_code=404, detail="Webhook subscription not found")
        return WebhookSubscriptionRecord.model_validate(subscription)

    @router.patch(
        "/api/v1/webhooks/{subscription_id}",
        response_model=WebhookSubscriptionRecord,
        dependencies=[Depends(require_admin_auth)],
    )
    def update_webhook(subscription_id: str, payload: WebhookSubscriptionUpdateRequest) -> WebhookSubscriptionRecord:
        target_url = (
            _validate_webhook_target_url(settings, payload.target_url)
            if payload.target_url is not None
            else None
        )
        subscription = repository.update_webhook_subscription(
            subscription_id,
            target_url=target_url,
            event_filter=payload.event_filter,
            enabled=payload.enabled,
        )
        if subscription is None:
            raise HTTPException(status_code=404, detail="Webhook subscription not found")
        return WebhookSubscriptionRecord.model_validate(subscription)

    @router.delete(
        "/api/v1/webhooks/{subscription_id}",
        response_model=WebhookDeleteResponse,
        dependencies=[Depends(require_admin_auth)],
    )
    def delete_webhook(subscription_id: str) -> WebhookDeleteResponse:
        deleted = repository.delete_webhook_subscription(subscription_id)
        if deleted is None:
            raise HTTPException(status_code=404, detail="Webhook subscription not found")
        return WebhookDeleteResponse.model_validate(deleted)

    @router.post(
        "/api/v1/webhooks/{subscription_id}/test",
        response_model=WebhookTestResponse,
        dependencies=[Depends(require_admin_auth)],
    )
    def test_webhook(request: Request, subscription_id: str) -> WebhookTestResponse:
        if repository.webhook_service is None:
            raise HTTPException(status_code=503, detail="Webhook delivery is unavailable")
        result = repository.webhook_service.send_test_event(
            subscription_id,
            actor=getattr(request.state, "audit_actor", None) or "admin_token",
            request_id=getattr(request.state, "request_id", None),
            ip_address=_request_ip(request),
        )
        return WebhookTestResponse.model_validate(result)

    @router.get(
        "/api/v1/webhooks/{subscription_id}/deliveries",
        response_model=WebhookDeliveryListResponse,
        dependencies=[Depends(require_admin_auth)],
    )
    def list_webhook_deliveries(
        subscription_id: str,
        limit: int = Query(default=50, ge=1, le=200),
        status: str | None = Query(default=None),
    ) -> WebhookDeliveryListResponse:
        if repository.get_webhook_subscription(subscription_id) is None:
            raise HTTPException(status_code=404, detail="Webhook subscription not found")
        return WebhookDeliveryListResponse.model_validate(
            repository.list_webhook_deliveries(subscription_id, limit=limit, status=status)
        )

    return router
