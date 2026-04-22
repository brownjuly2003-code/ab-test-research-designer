from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.backend.app.config import get_settings
from app.backend.app.frontend_routes import register_frontend_routes
from app.backend.app.http_runtime import (
    create_runtime_counters,
    register_exception_handlers,
    register_http_runtime,
)
from app.backend.app.http_utils import SlidingWindowRateLimiter, get_auth_mode
from app.backend.app.i18n import reset_current_language, resolve_language, set_current_language
from app.backend.app.logging_utils import configure_logging, log_event
from app.backend.app.repository import ProjectRepository
from app.backend.app.routes.audit import create_audit_router
from app.backend.app.routes import analysis as analysis_routes
from app.backend.app.routes.export import create_export_router
from app.backend.app.routes.keys import create_keys_router
from app.backend.app.routes.projects import create_projects_router
from app.backend.app.routes.system import create_system_router
from app.backend.app.routes.templates import create_templates_router
from app.backend.app.routes.webhooks import create_webhooks_router
from app.backend.app.routes.workspace import create_workspace_router
from app.backend.app.services.design_service import build_experiment_report
from app.backend.app.startup_seed import seed_demo_workspace
from app.backend.app.services.webhook_service import WebhookService

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(level=settings.log_level, log_format=settings.log_format)
    started_at = datetime.now(timezone.utc)
    repository = ProjectRepository(
        settings.db_path,
        busy_timeout_ms=settings.sqlite_busy_timeout_ms,
        journal_mode=settings.sqlite_journal_mode,
        synchronous=settings.sqlite_synchronous,
        workspace_signing_key=settings.workspace_signing_key,
    )
    webhook_service = WebhookService(repository, environment=settings.environment)
    repository.set_webhook_service(webhook_service)
    runtime_counters = create_runtime_counters()
    request_rate_limiter = SlidingWindowRateLimiter(
        max_requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )
    auth_failure_limiter = SlidingWindowRateLimiter(
        max_requests=settings.auth_failure_limit,
        window_seconds=settings.auth_failure_window_seconds,
    )
    cors_headers = list(settings.cors_headers)
    if settings.api_token or settings.readonly_api_token or settings.admin_token or repository.has_api_keys():
        for header_name in ("Authorization", "X-API-Key"):
            if header_name not in cors_headers:
                cors_headers.append(header_name)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        log_event(
            logger,
            logging.INFO,
            "application started",
            event="startup",
            environment=settings.environment,
            version=settings.app_version,
            db_path=settings.db_path,
            sqlite_journal_mode=settings.sqlite_journal_mode,
            sqlite_synchronous=settings.sqlite_synchronous,
            log_format=settings.log_format,
            auth_mode=get_auth_mode(
                settings.api_token,
                settings.readonly_api_token,
                repository.has_api_keys(),
            ),
            workspace_signing_enabled=settings.workspace_signing_key is not None,
        )
        if settings.seed_demo_on_startup:
            try:
                seed_demo_workspace(settings, repository)
            except Exception:
                logger.exception("demo-seed: failed")
        yield
        webhook_service.shutdown(wait=True)

    app = FastAPI(
        title="AB Test Research Designer API",
        version=settings.app_version,
        description=(
            "Public API for deterministic A/B and multivariate experiment planning. "
            "It combines calculations, project storage, audit history, export flows, "
            "and optional local AI advice while preserving legacy shared-token access."
        ),
        contact={"name": "AB Test Research Designer", "email": "support@example.invalid"},
        license_info={"name": "UNLICENSED"},
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=[
            {"name": "calculations", "description": "Deterministic experiment calculations and analysis."},
            {"name": "projects", "description": "Saved project CRUD, history, and reports."},
            {"name": "templates", "description": "Built-in and custom project templates."},
            {"name": "audit", "description": "Audit log listing and export."},
            {"name": "keys", "description": "Admin-only API key lifecycle management."},
            {"name": "webhooks", "description": "Admin-only outbound webhook subscription management."},
            {"name": "workspace", "description": "Workspace backup, restore, and export utilities."},
            {"name": "system", "description": "Health, readiness, and runtime diagnostics."},
        ],
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=list(settings.cors_methods),
        allow_headers=cors_headers,
    )

    @app.middleware("http")
    async def add_request_language(request: Request, call_next):
        language = resolve_language(request.headers.get("Accept-Language"))
        request.state.language = language
        language_token = set_current_language(language)
        try:
            response = await call_next(request)
        finally:
            reset_current_language(language_token)
        return response

    require_auth, require_write_auth, require_admin_auth = register_http_runtime(
        app,
        settings=settings,
        logger=logger,
        repository=repository,
        request_rate_limiter=request_rate_limiter,
        auth_failure_limiter=auth_failure_limiter,
        runtime_counters=runtime_counters,
    )
    register_exception_handlers(app, logger=logger)
    analysis_routes.build_experiment_report = build_experiment_report
    app.include_router(
        analysis_routes.create_analysis_router(
            settings,
            repository,
            request_rate_limiter,
            require_auth,
            require_write_auth,
        )
    )
    app.include_router(
        create_audit_router(
            settings,
            repository,
            request_rate_limiter,
            require_auth,
            require_write_auth,
        )
    )
    app.include_router(create_keys_router(settings, repository, require_admin_auth))
    app.include_router(create_webhooks_router(settings, repository, require_admin_auth))
    app.include_router(
        create_projects_router(
            settings,
            repository,
            request_rate_limiter,
            require_auth,
            require_write_auth,
        )
    )
    app.include_router(
        create_templates_router(
            settings,
            repository,
            request_rate_limiter,
            require_auth,
            require_write_auth,
        )
    )
    app.include_router(
        create_workspace_router(
            settings,
            repository,
            request_rate_limiter,
            require_auth,
            require_write_auth,
        )
    )
    app.include_router(create_export_router(settings, repository, request_rate_limiter, require_auth))
    app.include_router(create_system_router(settings, repository, runtime_counters, started_at))
    register_frontend_routes(app, settings)
    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("app.backend.app.main:app", host=settings.host, port=settings.port)
