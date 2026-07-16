"""Webhook subscription and delivery payloads."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WebhookSubscriptionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    target_url: str = Field(min_length=1, max_length=2000)
    secret: str = Field(min_length=1, max_length=200)
    format: Literal["generic", "slack"]
    event_filter: list[str] = Field(default_factory=list)
    scope: Literal["global", "api_key"]
    api_key_id: str | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> "WebhookSubscriptionCreateRequest":
        self.event_filter = [value.strip() for value in self.event_filter if value.strip()]
        if self.scope == "api_key" and not self.api_key_id:
            raise ValueError("api_key_id is required for api_key scope")
        if self.scope == "global" and self.api_key_id is not None:
            raise ValueError("api_key_id is not allowed for global scope")
        return self


class WebhookSubscriptionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    event_filter: list[str] | None = None
    target_url: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def normalize_event_filter(self) -> "WebhookSubscriptionUpdateRequest":
        if self.event_filter is not None:
            self.event_filter = [value.strip() for value in self.event_filter if value.strip()]
        return self


class WebhookSubscriptionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    target_url: str
    secret: str | None = None
    format: Literal["generic", "slack"]
    event_filter: list[str] = Field(default_factory=list)
    scope: Literal["global", "api_key"]
    api_key_id: str | None = None
    created_at: str
    updated_at: str
    last_delivered_at: str | None = None
    last_error_at: str | None = None
    enabled: bool = True


class WebhookDeliveryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    subscription_id: str
    event_id: int
    status: Literal["pending", "delivered", "failed", "retrying"]
    attempt_count: int
    last_attempt_at: str | None = None
    delivered_at: str | None = None
    response_code: int | None = None
    response_body: str | None = None
    error_message: str | None = None
    next_attempt_at: str | None = None
    lease_expires_at: str | None = None


class WebhookListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subscriptions: list[WebhookSubscriptionRecord]
    total: int = 0


class WebhookDeliveryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deliveries: list[WebhookDeliveryRecord]
    total: int = 0


class WebhookTestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delivery_id: str
    status: Literal["delivered", "failed", "retrying", "pending"]
    response_code: int | None = None


class WebhookDeleteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    deleted: bool
