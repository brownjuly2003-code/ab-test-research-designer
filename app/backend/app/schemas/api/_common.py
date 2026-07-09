"""Error envelope shared by every route."""

from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: Any
    error_code: str
    status_code: int
    request_id: str
