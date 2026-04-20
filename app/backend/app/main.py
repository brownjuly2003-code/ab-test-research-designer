from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging

from fastapi import FastAPI
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
from app.backend.app.logging_utils import configure_logging, log_event
from app.backend.app.repository import ProjectRepository
from app.backend.app.routes import analysis as analysis_routes
from app.backend.app.routes.export import create_export_router
from app.backend.app.routes.projects import create_projects_router
from app.backend.app.routes.system import create_system_router
from app.backend.app.routes.workspace import create_workspace_router
from app.backend.app.services.design_service import build_experiment_report

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
    if settings.api_token or settings.readonly_api_token:
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
            auth_mode=get_auth_mode(settings.api_token, settings.readonly_api_token),
            workspace_signing_enabled=settings.workspace_signing_key is not None,
        )
        yield

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Local backend for A/B experiment planning.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=list(settings.cors_methods),
        allow_headers=cors_headers,
    )
    require_auth, require_write_auth = register_http_runtime(
        app,
        settings=settings,
        logger=logger,
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
        create_projects_router(
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
