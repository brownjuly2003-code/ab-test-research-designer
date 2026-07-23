import hmac
import logging
import uuid
from collections.abc import Callable
from datetime import UTC
from time import perf_counter
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.background import BackgroundTask, BackgroundTasks
from starlette.middleware.base import RequestResponseEndpoint

from app.backend.app.errors import ApiError
from app.backend.app.http_utils import (
    AUTH_READ_ONLY_METHODS,
    HTTP_413_BODY_TOO_LARGE,
    PUBLIC_COMPUTE_PATHS,
    RequestBodyTooLargeError,
    apply_standard_response_headers,
    buffer_request_body_with_limit,
    build_auth_failure_response,
    build_error_response,
    extract_presented_token,
    get_auth_mode,
    get_client_identifier,
    get_http_error_code,
    get_process_time_ms,
    get_request_body_limit,
    get_request_id,
    is_heavy_compute_path,
    is_protected_path,
    is_rate_limited_path,
    is_slack_ingress_path,
)
from app.backend.app.logging_utils import log_event

if TYPE_CHECKING:
    from app.backend.app.config import Settings
    from app.backend.app.http_utils import SlidingWindowRateLimiter
    from app.backend.app.repository import ProjectRepository


def create_runtime_counters() -> dict[str, int | float | str | None]:
    return {
        "total_requests": 0,
        "success_responses": 0,
        "client_error_responses": 0,
        "server_error_responses": 0,
        "auth_rejections": 0,
        "rate_limited_responses": 0,
        "request_body_rejections": 0,
        "compute_capacity_rejections": 0,
        "last_request_at": None,
        "last_error_at": None,
        "last_error_code": None,
        # RED latency accumulators (process-local; audit F-12).
        "process_time_ms_sum": 0.0,
        "process_time_ms_count": 0,
        "process_time_ms_max": 0.0,
    }


def build_runtime_summary(runtime_counters: dict[str, Any]) -> dict[str, Any]:
    """Project raw counters into the diagnostics RuntimeSummary shape."""
    total = int(runtime_counters.get("total_requests") or 0)
    client_errors = int(runtime_counters.get("client_error_responses") or 0)
    server_errors = int(runtime_counters.get("server_error_responses") or 0)
    timed = int(runtime_counters.get("process_time_ms_count") or 0)
    time_sum = float(runtime_counters.get("process_time_ms_sum") or 0.0)
    time_max = float(runtime_counters.get("process_time_ms_max") or 0.0)
    error_rate = round((client_errors + server_errors) / total, 6) if total else 0.0
    return {
        "total_requests": total,
        "success_responses": int(runtime_counters.get("success_responses") or 0),
        "client_error_responses": client_errors,
        "server_error_responses": server_errors,
        "auth_rejections": int(runtime_counters.get("auth_rejections") or 0),
        "rate_limited_responses": int(runtime_counters.get("rate_limited_responses") or 0),
        "request_body_rejections": int(runtime_counters.get("request_body_rejections") or 0),
        "compute_capacity_rejections": int(runtime_counters.get("compute_capacity_rejections") or 0),
        "last_request_at": runtime_counters.get("last_request_at"),
        "last_error_at": runtime_counters.get("last_error_at"),
        "last_error_code": runtime_counters.get("last_error_code"),
        "process_time_ms_count": timed,
        "process_time_ms_avg": round(time_sum / timed, 3) if timed else None,
        "process_time_ms_max": round(time_max, 3) if timed else None,
        "error_rate": error_rate,
    }


def register_http_runtime(
    app: FastAPI,
    *,
    settings: "Settings",
    logger: logging.Logger,
    repository: "ProjectRepository",
    request_rate_limiter: "SlidingWindowRateLimiter",
    auth_failure_limiter: "SlidingWindowRateLimiter",
    runtime_counters: dict[str, Any],
) -> tuple[
    Callable[[Request], None],
    Callable[[Request], None],
    Callable[[Request], None],
]:
    def record_runtime_response(
        status_code: int,
        error_code: str | None = None,
        *,
        auth_rejection: bool = False,
        process_time_ms: float | None = None,
    ) -> None:
        from datetime import datetime

        timestamp = datetime.now(UTC).isoformat()
        runtime_counters["total_requests"] += 1
        runtime_counters["last_request_at"] = timestamp
        if status_code >= 500:
            runtime_counters["server_error_responses"] += 1
        elif status_code >= 400:
            runtime_counters["client_error_responses"] += 1
        else:
            runtime_counters["success_responses"] += 1
        if auth_rejection:
            runtime_counters["auth_rejections"] += 1
        if error_code in {"rate_limited", "auth_rate_limited", "slack_invalid_signature_rate_limited"}:
            runtime_counters["rate_limited_responses"] += 1
        if error_code == "request_body_too_large":
            runtime_counters["request_body_rejections"] += 1
        if error_code == "compute_capacity_exceeded":
            runtime_counters["compute_capacity_rejections"] += 1
        if error_code:
            runtime_counters["last_error_at"] = timestamp
            runtime_counters["last_error_code"] = error_code
        if process_time_ms is not None:
            runtime_counters["process_time_ms_sum"] = (
                float(runtime_counters["process_time_ms_sum"]) + float(process_time_ms)
            )
            runtime_counters["process_time_ms_count"] = int(runtime_counters["process_time_ms_count"]) + 1
            runtime_counters["process_time_ms_max"] = max(
                float(runtime_counters["process_time_ms_max"]),
                float(process_time_ms),
            )

    def auth_enabled() -> bool:
        # Any auth material at all closes the protected surface; anonymous callers
        # then get 401 instead of an open door.
        #
        # admin_token counts. An admin-only deployment is a legitimate bootstrap —
        # the admin token exists to issue the first write API key — and omitting it
        # here left keys/webhooks protected while ordinary project mutations stayed
        # open to anonymous callers.
        #
        # public_demo alone (no tokens configured) still forces anonymous sessions
        # into the read scope — a hosted demo must never expose open mutations.
        #
        # has_api_keys() is last on purpose: it hits the database, so the static
        # settings short-circuit it on every request of a token-configured deployment.
        return bool(
            settings.api_token
            or settings.readonly_api_token
            or settings.admin_token
            or settings.public_demo
            or repository.has_api_keys()
        )

    def require_auth(request: Request) -> None:
        if not auth_enabled():
            return
        if getattr(request.state, "auth_scope", None) in {"read", "write", "admin"}:
            return
        raise HTTPException(status_code=401, detail="Unauthorized")

    def require_write_auth(request: Request) -> None:
        if not auth_enabled():
            return
        auth_scope = getattr(request.state, "auth_scope", None)
        if auth_scope in {"write", "admin"}:
            return
        if auth_scope == "read":
            raise HTTPException(status_code=403, detail="Forbidden")
        raise HTTPException(status_code=401, detail="Unauthorized")

    def require_admin_auth(request: Request) -> None:
        if not settings.admin_token:
            raise HTTPException(status_code=401, detail="Unauthorized")
        if getattr(request.state, "admin_authenticated", False):
            return
        if getattr(request.state, "auth_scope", None) in {"read", "write"}:
            raise HTTPException(status_code=403, detail="Forbidden")
        raise HTTPException(status_code=401, detail="Unauthorized")

    @app.middleware("http")
    async def add_request_metadata(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        started = perf_counter()
        request.state.request_id = request_id
        request.state.request_started = started
        request.state.auth_scope = None
        request.state.auth_source = None
        request.state.auth_key_id = None
        request.state.audit_actor = None
        request.state.admin_authenticated = False
        request.state.rate_limit_bucket_key = None
        request.state.rate_limit_requests = None
        request.state.rate_limit_window_seconds = None
        request.state.pending_api_key_audit = None

        def attach_pending_api_key_audit(response: Response) -> None:
            pending_audit = getattr(request.state, "pending_api_key_audit", None)
            if pending_audit is None or response.status_code >= 500:
                return
            request.state.pending_api_key_audit = None
            audit_task = BackgroundTask(
                repository.log_audit_entry,
                action="api_key_used",
                **pending_audit,
            )
            existing = response.background
            if existing is None:
                response.background = audit_task
            elif isinstance(existing, BackgroundTasks):
                existing.tasks.append(audit_task)
            else:
                response.background = BackgroundTasks(tasks=[existing, audit_task])

        def finalize_response(response: Response) -> Response:
            attach_pending_api_key_audit(response)
            return apply_standard_response_headers(
                response,
                request_id=request_id,
                process_time_ms=(perf_counter() - started) * 1000,
            )

        def reject_auth_request(
            *,
            detail: str,
            response_status: int,
            error_code: str,
            auth_scope: str | None = None,
        ) -> Response:
            auth_limit_headers: dict[str, str] | None = None
            resolved_status = response_status
            resolved_detail = detail
            resolved_error_code = error_code
            if settings.rate_limit_enabled:
                auth_limit_decision = auth_failure_limiter.allow(f"auth:{get_client_identifier(request, settings)}")
                if not auth_limit_decision.allowed:
                    auth_limit_headers = {"Retry-After": str(auth_limit_decision.retry_after_seconds)}
                    resolved_error_code = "auth_rate_limited"
                    resolved_status = status.HTTP_429_TOO_MANY_REQUESTS
                    resolved_detail = "Too many unauthorized requests"
            response = build_auth_failure_response(request, resolved_detail, resolved_status, resolved_error_code)
            if auth_limit_headers:
                for header_name, header_value in auth_limit_headers.items():
                    response.headers[header_name] = header_value
            log_event(
                logger,
                logging.WARNING,
                "request rejected",
                event="http_request_auth",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                process_time_ms=round(get_process_time_ms(request), 2),
                auth_mode=get_auth_mode(
                    settings.api_token,
                    settings.readonly_api_token,
                    repository.has_api_keys(),
                ),
                auth_scope=auth_scope,
                error_code=resolved_error_code,
            )
            record_runtime_response(
                response.status_code,
                resolved_error_code,
                auth_rejection=True,
                process_time_ms=(perf_counter() - started) * 1000,
            )
            return finalize_response(response)

        if request.method != "OPTIONS" and is_protected_path(request.url.path):
            presented_token = extract_presented_token(request)
            admin_only_path = request.url.path.startswith("/api/v1/keys") or request.url.path.startswith("/api/v1/webhooks")
            if admin_only_path:
                if settings.admin_token and presented_token is not None and hmac.compare_digest(presented_token, settings.admin_token):
                    request.state.admin_authenticated = True
                    request.state.auth_scope = "admin"
                    request.state.auth_source = "admin_token"
                    request.state.audit_actor = "admin_token"
            auth_required = admin_only_path or auth_enabled()
            if auth_required and not request.state.admin_authenticated:
                if settings.api_token and presented_token is not None and hmac.compare_digest(presented_token, settings.api_token):
                    request.state.auth_scope = "write"
                    request.state.auth_source = "legacy"
                    request.state.audit_actor = "legacy_token:write"
                elif (
                    settings.readonly_api_token
                    and presented_token is not None
                    and hmac.compare_digest(presented_token, settings.readonly_api_token)
                ):
                    request.state.auth_scope = "read"
                    request.state.auth_source = "legacy"
                    request.state.audit_actor = "legacy_token:read"
                elif presented_token is not None:
                    api_key = repository.authenticate_api_key(presented_token)
                    if api_key is None:
                        return reject_auth_request(
                            detail="Unauthorized",
                            response_status=status.HTTP_401_UNAUTHORIZED,
                            error_code="unauthorized",
                        )
                    request.state.auth_scope = api_key["scope"]
                    request.state.auth_source = "api_key"
                    request.state.auth_key_id = api_key["id"]
                    request.state.audit_actor = f"api_key:{api_key['id']}"
                    request.state.rate_limit_bucket_key = f"api_key:{api_key['id']}"
                    request.state.rate_limit_requests = api_key.get("rate_limit_requests")
                    request.state.rate_limit_window_seconds = api_key.get("rate_limit_window_seconds")
                    request.state.pending_api_key_audit = {
                        "key_id": api_key["id"],
                        "actor": request.state.audit_actor,
                        "request_id": request_id,
                        "ip_address": get_client_identifier(request, settings),
                    }
                elif settings.public_demo and not admin_only_path:
                    # Public demo mode: an anonymous visitor gets a read-scope
                    # session instead of a 401 so the hosted demo is browsable
                    # (and its calculators usable) without handing out tokens.
                    # Admin-only surfaces (keys/webhooks) keep rejecting.
                    request.state.auth_scope = "read"
                    request.state.auth_source = "anonymous"
                    request.state.audit_actor = "anonymous"
                else:
                    return reject_auth_request(
                        detail="Unauthorized",
                        response_status=status.HTTP_401_UNAUTHORIZED,
                        error_code="unauthorized",
                    )

                if (
                    getattr(request.state, "auth_scope", None) == "read"
                    and request.method not in AUTH_READ_ONLY_METHODS
                    # Read-only means "cannot change stored state": stateless
                    # compute POSTs stay available to read-scope sessions.
                    and request.url.path not in PUBLIC_COMPUTE_PATHS
                ):
                    return reject_auth_request(
                        detail="Forbidden",
                        response_status=status.HTTP_403_FORBIDDEN,
                        error_code="forbidden",
                        auth_scope="read",
                    )

        if settings.rate_limit_enabled and request.method != "OPTIONS" and is_rate_limited_path(request.url.path):
            client_id = get_client_identifier(request, settings)
            if is_slack_ingress_path(request.url.path):
                # Dedicated Slack bucket: slash retries and interactive actions
                # should not share the CRUD-sized /api/v1 window, and invalid
                # traffic is further throttled after signature failure in routes.
                rate_limit_decision = request_rate_limiter.allow(
                    f"slack:{client_id}",
                    max_requests=settings.slack_rate_limit_requests,
                    window_seconds=settings.slack_rate_limit_window_seconds,
                )
            else:
                bucket_base = getattr(request.state, "rate_limit_bucket_key", None) or f"api:{client_id}"
                rate_limit_decision = request_rate_limiter.allow(
                    bucket_base,
                    max_requests=getattr(request.state, "rate_limit_requests", None),
                    window_seconds=getattr(request.state, "rate_limit_window_seconds", None),
                )
                if rate_limit_decision.allowed and request.method == "POST" and is_heavy_compute_path(request.url.path):
                    # Second, tighter bucket for simulation endpoints: the global
                    # window is sized for CRUD traffic, and a caller staying inside
                    # it can still keep a demo CPU pegged with Monte-Carlo requests.
                    rate_limit_decision = request_rate_limiter.allow(
                        f"heavy:{bucket_base}",
                        max_requests=settings.heavy_rate_limit_requests,
                        window_seconds=settings.heavy_rate_limit_window_seconds,
                    )
            if not rate_limit_decision.allowed:
                response: Response = build_error_response(
                    request,
                    detail="Too many requests",
                    error_code="rate_limited",
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    extra_headers={"Retry-After": str(rate_limit_decision.retry_after_seconds)},
                )
                log_event(
                    logger,
                    logging.WARNING,
                    "request rate limited",
                    event="http_request_rate_limit",
                    request_id=request_id,
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    process_time_ms=round(get_process_time_ms(request), 2),
                    retry_after_seconds=rate_limit_decision.retry_after_seconds,
                )
                record_runtime_response(
                    response.status_code,
                    "rate_limited",
                    process_time_ms=(perf_counter() - started) * 1000,
                )
                return finalize_response(response)

        body_limit = get_request_body_limit(request.url.path, request.method, settings)
        if body_limit is not None:
            try:
                await buffer_request_body_with_limit(request, body_limit)
            except RequestBodyTooLargeError:
                response = build_error_response(
                    request,
                    detail=f"Request body exceeds limit of {body_limit} bytes",
                    error_code="request_body_too_large",
                    status_code=HTTP_413_BODY_TOO_LARGE,
                )
                log_event(
                    logger,
                    logging.WARNING,
                    "request body rejected",
                    event="http_request_body_limit",
                    request_id=request_id,
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    process_time_ms=round(get_process_time_ms(request), 2),
                    max_body_bytes=body_limit,
                )
                record_runtime_response(
                    response.status_code,
                    "request_body_too_large",
                    process_time_ms=(perf_counter() - started) * 1000,
                )
                return finalize_response(response)

        try:
            response = await call_next(request)
        except Exception:
            log_event(
                logger,
                logging.ERROR,
                "request failed",
                event="http_request",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                process_time_ms=round(get_process_time_ms(request), 2),
            )
            raise

        attach_pending_api_key_audit(response)
        process_time_ms = (perf_counter() - started) * 1000
        apply_standard_response_headers(response, request_id=request_id, process_time_ms=process_time_ms)
        record_runtime_response(
            response.status_code,
            response.headers.get("X-Error-Code"),
            process_time_ms=process_time_ms,
        )
        log_event(
            logger,
            logging.INFO,
            "request completed",
            event="http_request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            process_time_ms=round(process_time_ms, 2),
        )
        return response

    return require_auth, require_write_auth, require_admin_auth


def register_exception_handlers(app: FastAPI, *, logger: logging.Logger, settings: "Settings") -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        log_event(
            logger,
            logging.WARNING if exc.status_code < 500 else logging.ERROR,
            "api error handled",
            event="http_request_error",
            request_id=get_request_id(request),
            method=request.method,
            path=request.url.path,
            status_code=exc.status_code,
            error_code=exc.error_code,
            process_time_ms=round(get_process_time_ms(request), 2),
        )
        return build_error_response(
            request,
            detail=exc.detail,
            error_code=exc.error_code,
            status_code=exc.status_code,
            extra_headers=exc.headers or None,
        )

    @app.exception_handler(ValueError)
    async def handle_value_error(request: Request, exc: ValueError) -> JSONResponse:
        log_event(
            logger,
            logging.WARNING,
            "value error handled",
            event="http_request_error",
            request_id=get_request_id(request),
            method=request.method,
            path=request.url.path,
            status_code=400,
            error_code="bad_request",
            process_time_ms=round(get_process_time_ms(request), 2),
            detail=str(exc),
        )
        # Local/demo keep the raw message: most ValueErrors here are intentional
        # input validation (webhook URL rules, stats parameter bounds) and the
        # text is the user-facing explanation. Production returns a generic
        # detail so an unexpected ValueError from deeper code cannot reflect
        # internals to API clients; the full message stays in the log above.
        detail = "Invalid value" if settings.is_production else str(exc)
        return build_error_response(request, detail=detail, error_code="bad_request", status_code=400)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return build_error_response(
            request,
            detail=jsonable_encoder(exc.errors()),
            error_code="validation_error",
            status_code=422,
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        return build_error_response(
            request,
            detail=exc.detail,
            error_code=get_http_error_code(exc.status_code),
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception while serving %s %s", request.method, request.url.path, exc_info=exc)
        return build_error_response(
            request,
            detail="Internal server error",
            error_code="internal_error",
            status_code=500,
        )
