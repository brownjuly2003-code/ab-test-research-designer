import hmac
import logging
from time import perf_counter
import uuid

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.backend.app.errors import ApiError
from app.backend.app.http_utils import (
    AUTH_READ_ONLY_METHODS,
    HTTP_413_BODY_TOO_LARGE,
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
    is_protected_path,
    is_rate_limited_path,
)
from app.backend.app.logging_utils import log_event


def create_runtime_counters() -> dict[str, int | str | None]:
    return {
        "total_requests": 0,
        "success_responses": 0,
        "client_error_responses": 0,
        "server_error_responses": 0,
        "auth_rejections": 0,
        "rate_limited_responses": 0,
        "request_body_rejections": 0,
        "last_request_at": None,
        "last_error_at": None,
        "last_error_code": None,
    }


def register_http_runtime(
    app: FastAPI,
    *,
    settings,
    logger: logging.Logger,
    repository,
    request_rate_limiter,
    auth_failure_limiter,
    runtime_counters: dict,
):
    def record_runtime_response(status_code: int, error_code: str | None = None, *, auth_rejection: bool = False) -> None:
        from datetime import datetime, timezone

        timestamp = datetime.now(timezone.utc).isoformat()
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
        if error_code in {"rate_limited", "auth_rate_limited"}:
            runtime_counters["rate_limited_responses"] += 1
        if error_code == "request_body_too_large":
            runtime_counters["request_body_rejections"] += 1
        if error_code:
            runtime_counters["last_error_at"] = timestamp
            runtime_counters["last_error_code"] = error_code

    def require_auth(request: Request) -> None:
        if not (settings.api_token or settings.readonly_api_token or repository.has_api_keys()):
            return
        if getattr(request.state, "auth_scope", None) in {"read", "write", "admin"}:
            return
        raise HTTPException(status_code=401, detail="Unauthorized")

    def require_write_auth(request: Request) -> None:
        if not (settings.api_token or settings.readonly_api_token or repository.has_api_keys()):
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
    async def add_request_metadata(request: Request, call_next):
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

        def finalize_response(response: Response) -> Response:
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
                auth_limit_decision = auth_failure_limiter.allow(f"auth:{get_client_identifier(request)}")
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
            record_runtime_response(response.status_code, resolved_error_code, auth_rejection=True)
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
            auth_required = admin_only_path or settings.api_token or settings.readonly_api_token or repository.has_api_keys()
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
                    repository.log_audit_entry(
                        action="api_key_used",
                        key_id=api_key["id"],
                        actor=request.state.audit_actor,
                        request_id=request_id,
                        ip_address=get_client_identifier(request),
                    )
                else:
                    return reject_auth_request(
                        detail="Unauthorized",
                        response_status=status.HTTP_401_UNAUTHORIZED,
                        error_code="unauthorized",
                    )

                if getattr(request.state, "auth_scope", None) == "read" and request.method not in AUTH_READ_ONLY_METHODS:
                    return reject_auth_request(
                        detail="Forbidden",
                        response_status=status.HTTP_403_FORBIDDEN,
                        error_code="forbidden",
                        auth_scope="read",
                    )

        if settings.rate_limit_enabled and request.method != "OPTIONS" and is_rate_limited_path(request.url.path):
            rate_limit_decision = request_rate_limiter.allow(
                getattr(request.state, "rate_limit_bucket_key", None) or f"api:{get_client_identifier(request)}",
                max_requests=getattr(request.state, "rate_limit_requests", None),
                window_seconds=getattr(request.state, "rate_limit_window_seconds", None),
            )
            if not rate_limit_decision.allowed:
                response = build_error_response(
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
                record_runtime_response(response.status_code, "rate_limited")
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
                record_runtime_response(response.status_code, "request_body_too_large")
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

        process_time_ms = (perf_counter() - started) * 1000
        apply_standard_response_headers(response, request_id=request_id, process_time_ms=process_time_ms)
        record_runtime_response(response.status_code, response.headers.get("X-Error-Code"))
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


def register_exception_handlers(app: FastAPI, *, logger: logging.Logger) -> None:
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
        return build_error_response(request, detail=exc.detail, error_code=exc.error_code, status_code=exc.status_code)

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
        )
        return build_error_response(request, detail=str(exc), error_code="bad_request", status_code=400)

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
