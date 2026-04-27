from collections import deque
from dataclasses import dataclass
from math import ceil
from threading import Lock
from time import monotonic, perf_counter
import uuid

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse

from app.backend.app.schemas.api import ErrorResponse

if hasattr(status, "HTTP_413_CONTENT_TOO_LARGE"):
    HTTP_413_BODY_TOO_LARGE = status.HTTP_413_CONTENT_TOO_LARGE
else:  # pragma: no cover - compatibility path for older Starlette/FastAPI builds
    HTTP_413_BODY_TOO_LARGE = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE

AUTH_EXEMPT_PREFIXES = ("/assets",)
AUTH_PROTECTED_EXACT_PATHS = {"/readyz"}
AUTH_READ_ONLY_METHODS = {"GET", "HEAD", "OPTIONS"}
RATE_LIMITED_PATH_PREFIXES = ("/api/v1",)
BODY_LIMITED_METHODS = {"POST", "PUT", "PATCH"}
WORKSPACE_BUNDLE_PATHS = {"/api/v1/workspace/import", "/api/v1/workspace/validate"}
SECURITY_RESPONSE_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; "
        "base-uri 'self'; "
        "connect-src 'self'; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "img-src 'self' data:; "
        "object-src 'none'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com"
    ),
    "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


class SlidingWindowRateLimiter:
    _PRUNE_INTERVAL = 1000

    def __init__(self, *, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = {}
        self._key_window: dict[str, int] = {}
        self._lock = Lock()
        self._calls_since_prune = 0

    def allow(
        self,
        key: str,
        *,
        max_requests: int | None = None,
        window_seconds: int | None = None,
    ) -> RateLimitDecision:
        resolved_max_requests = max_requests or self.max_requests
        resolved_window_seconds = window_seconds or self.window_seconds
        now = monotonic()
        with self._lock:
            self._calls_since_prune += 1
            if self._calls_since_prune >= self._PRUNE_INTERVAL:
                self._prune_locked(now)
                self._calls_since_prune = 0
            bucket = self._events.setdefault(key, deque())
            self._key_window[key] = max(
                self._key_window.get(key, 0),
                resolved_window_seconds,
            )
            window_start = now - resolved_window_seconds
            while bucket and bucket[0] <= window_start:
                bucket.popleft()
            if len(bucket) >= resolved_max_requests:
                retry_after_seconds = max(1, ceil(bucket[0] + resolved_window_seconds - now))
                return RateLimitDecision(allowed=False, retry_after_seconds=retry_after_seconds)
            bucket.append(now)
            return RateLimitDecision(allowed=True)

    def _prune_locked(self, now: float) -> None:
        stale_keys: list[str] = []
        for key, bucket in self._events.items():
            window = self._key_window.get(key, self.window_seconds)
            cutoff = now - window
            if not bucket or bucket[-1] <= cutoff:
                stale_keys.append(key)
        for key in stale_keys:
            del self._events[key]
            self._key_window.pop(key, None)


def is_protected_path(path: str) -> bool:
    if path.startswith("/api/v1"):
        return True
    if path in AUTH_PROTECTED_EXACT_PATHS:
        return True
    if any(path.startswith(prefix) for prefix in AUTH_EXEMPT_PREFIXES):
        return False
    return False


def is_rate_limited_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in RATE_LIMITED_PATH_PREFIXES)


def get_client_identifier(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        first_hop = forwarded_for.split(",", maxsplit=1)[0].strip()
        if first_hop:
            return first_hop
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def get_request_body_limit(path: str, method: str, settings) -> int | None:
    if method not in BODY_LIMITED_METHODS:
        return None
    if path in WORKSPACE_BUNDLE_PATHS:
        return settings.max_workspace_body_bytes
    if path.startswith("/api/v1"):
        return settings.max_request_body_bytes
    return None


def extract_presented_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        return token or None
    api_key = request.headers.get("x-api-key", "").strip()
    return api_key or None


def get_auth_mode(
    write_token: str | None,
    readonly_token: str | None,
    api_keys_enabled: bool = False,
) -> str:
    if api_keys_enabled and (write_token or readonly_token):
        return "hybrid"
    if api_keys_enabled:
        return "api_keys"
    if write_token and readonly_token:
        return "dual_token"
    if write_token:
        return "token"
    if readonly_token:
        return "readonly"
    return "open"


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


def get_process_time_ms(request: Request) -> float:
    started = getattr(request.state, "request_started", None)
    if started is None:
        return 0.0
    return (perf_counter() - started) * 1000


def apply_standard_response_headers(
    response: Response,
    *,
    request_id: str | None = None,
    process_time_ms: float | None = None,
) -> Response:
    if request_id is not None:
        response.headers["X-Request-ID"] = request_id
    if process_time_ms is not None:
        response.headers["X-Process-Time-Ms"] = f"{process_time_ms:.2f}"
    for header_name, header_value in SECURITY_RESPONSE_HEADERS.items():
        response.headers.setdefault(header_name, header_value)
    return response


class RequestBodyTooLargeError(Exception):
    def __init__(self, limit_bytes: int) -> None:
        super().__init__(f"Request body exceeds limit of {limit_bytes} bytes")
        self.limit_bytes = limit_bytes


async def buffer_request_body_with_limit(request: Request, max_bytes: int) -> None:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise RequestBodyTooLargeError(max_bytes)
        except ValueError:
            pass
    if hasattr(request, "_body"):
        if len(getattr(request, "_body")) > max_bytes:
            raise RequestBodyTooLargeError(max_bytes)
        return
    buffered_chunks: list[bytes] = []
    buffered_size = 0
    more_body = True
    while more_body:
        message = await request._receive()
        chunk = message.get("body", b"")
        buffered_size += len(chunk)
        if buffered_size > max_bytes:
            raise RequestBodyTooLargeError(max_bytes)
        if chunk:
            buffered_chunks.append(chunk)
        more_body = message.get("more_body", False)
    buffered_body = b"".join(buffered_chunks)
    request._body = buffered_body
    replayed = False

    async def replay_receive() -> dict[str, object]:
        nonlocal replayed
        if replayed:
            return {"type": "http.request", "body": b"", "more_body": False}
        replayed = True
        return {"type": "http.request", "body": buffered_body, "more_body": False}

    request._receive = replay_receive


def build_error_response(
    request: Request,
    *,
    detail: str | list[dict] | dict,
    error_code: str,
    status_code: int,
    extra_headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = get_request_id(request)
    process_time_ms = get_process_time_ms(request)
    response = JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            detail=detail,
            error_code=error_code,
            status_code=status_code,
            request_id=request_id,
        ).model_dump(),
        headers=extra_headers or {},
    )
    apply_standard_response_headers(response, request_id=request_id, process_time_ms=process_time_ms)
    response.headers["X-Error-Code"] = error_code
    return response


def build_auth_failure_response(
    request: Request,
    detail: str,
    status_code: int,
    error_code: str,
) -> JSONResponse:
    extra_headers = {"WWW-Authenticate": "Bearer"} if status_code == status.HTTP_401_UNAUTHORIZED else None
    return build_error_response(
        request,
        detail=detail,
        error_code=error_code,
        status_code=status_code,
        extra_headers=extra_headers,
    )


def get_http_error_code(status_code: int) -> str:
    if status_code == status.HTTP_401_UNAUTHORIZED:
        return "unauthorized"
    if status_code == status.HTTP_403_FORBIDDEN:
        return "forbidden"
    if status_code == status.HTTP_404_NOT_FOUND:
        return "not_found"
    return "http_error"
