"""API-key payloads."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    # Issued keys are read or write only. Operator/bootstrap access is the static
    # AB_ADMIN_TOKEN, not a revocable DB key (audit F-09).
    scope: Literal["read", "write"]
    rate_limit_requests: int | None = Field(default=None, ge=1)
    rate_limit_window_seconds: int | None = Field(default=None, ge=1)


class ApiKeyRecord(BaseModel):
    id: str
    name: str
    scope: Literal["read", "write"]
    created_at: str
    last_used_at: str | None = None
    revoked_at: str | None = None
    rate_limit_requests: int | None = None
    rate_limit_window_seconds: int | None = None


class ApiKeyCreateResponse(ApiKeyRecord):
    plaintext_key: str


class ApiKeyListResponse(BaseModel):
    keys: list[ApiKeyRecord]
    total: int = 0


class ApiKeyDeleteResponse(BaseModel):
    id: str
    deleted: bool
