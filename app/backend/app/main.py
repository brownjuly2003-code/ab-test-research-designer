import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint

from app.backend.app.config import Settings, get_settings
from app.backend.app.frontend_routes import register_frontend_routes
from app.backend.app.http_runtime import (
    create_runtime_counters,
    register_exception_handlers,
    register_http_runtime,
)
from app.backend.app.http_utils import SlidingWindowRateLimiter, get_auth_mode
from app.backend.app.i18n import (
    reset_current_language,
    resolve_language,
    set_current_language,
)
from app.backend.app.logging_utils import configure_logging, log_event
from app.backend.app.redaction import redact_database_url
from app.backend.app.repository import ProjectRepository
from app.backend.app.routes import analysis as analysis_routes
from app.backend.app.routes.audit import create_audit_router
from app.backend.app.routes.execution import create_execution_router
from app.backend.app.routes.export import create_export_router
from app.backend.app.routes.keys import create_keys_router
from app.backend.app.routes.projects import create_projects_router
from app.backend.app.routes.slack import create_slack_router
from app.backend.app.routes.system import create_system_router
from app.backend.app.routes.templates import create_templates_router
from app.backend.app.routes.webhooks import create_webhooks_router
from app.backend.app.routes.workspace import create_workspace_router
from app.backend.app.services.design_service import build_experiment_report
from app.backend.app.services.snapshot_service import SnapshotService
from app.backend.app.services.webhook_service import WebhookService
from app.backend.app.startup_seed import seed_demo_workspace

logger = logging.getLogger(__name__)


def _verify_production_storage(repository: ProjectRepository) -> None:
    """Fail fast in production unless the durable PostgreSQL backend is live and writable.

    Config validation already requires a PostgreSQL ``AB_DATABASE_URL`` in production
    (``config._validate_settings``); this confirms the backend actually resolved to
    PostgreSQL and that a real write-probe succeeds before the process starts serving,
    turning "config says PG" into "PG is reachable and writable".
    """
    if repository.backend_name != "postgres":
        raise RuntimeError(
            "Production mode requires the PostgreSQL backend; resolved backend is "
            f"{repository.backend_name!r}. Set AB_DATABASE_URL to a postgres:// URL."
        )
    summary = repository.get_diagnostics_summary()
    if not summary.get("write_probe_ok", False):
        detail = summary.get("write_probe_detail", "unknown error")
        raise RuntimeError(f"Production storage health check failed: {detail}")


def _verify_production_auth(settings: Settings, repository: ProjectRepository) -> None:
    """Fail fast in production unless some auth material can gate mutating endpoints.

    Without this, ``AB_ENV=production`` starts happily with no tokens at all:
    ``http_runtime.auth_enabled()`` returns False, ``require_write_auth`` waves every
    request through, and the whole write surface (projects, templates, ingestion,
    workspace restore) is open to anonymous callers. "Forgot to set a token" is the
    one production mistake that must not boot.

    Three bootstraps are accepted, because each one ends with anonymous writes rejected:

    - ``AB_API_TOKEN`` — the write-scoped shared token;
    - ``AB_ADMIN_TOKEN`` — no write scope of its own, but it can issue the first
      write-scoped API key through ``/api/v1/keys`` (and it already makes
      ``auth_enabled()`` true, so mutations answer 401 until that key exists);
    - an active write-scoped API key already in the database — the steady state after
      the admin token has been retired.

    A read-only token or ``AB_PUBLIC_DEMO`` alone is deliberately *not* enough: nothing
    is open, but nothing can be written either, so it is a broken production config
    rather than a secure one.

    This check lives here rather than in ``config._validate_settings`` because the third
    bootstrap is a fact about the database, which config cannot see. Startup is the first
    point where both the settings and a live repository exist. It runs after
    ``_verify_production_storage`` so an unreachable database reports itself as a storage
    failure instead of surfacing as a driver error from the API-key lookup below.

    ``AB_ALLOW_INSECURE_PRODUCTION=true`` is the explicit, loudly logged opt-out.
    """
    if settings.api_token or settings.admin_token:
        return
    if repository.has_active_api_keys(scope="write"):
        return
    if settings.allow_insecure_production:
        log_event(
            logger,
            logging.WARNING,
            "INSECURE PRODUCTION: no auth material is configured, so every mutating endpoint "
            "is open to anonymous callers. AB_ALLOW_INSECURE_PRODUCTION=true suppressed the "
            "startup check that would normally refuse to boot.",
            event="insecure_production",
            environment=settings.environment,
            remediation=(
                "Set AB_API_TOKEN, or set AB_ADMIN_TOKEN and issue a write-scoped API key, "
                "then unset AB_ALLOW_INSECURE_PRODUCTION. See docs/PRODUCTION.md."
            ),
        )
        return
    raise RuntimeError(
        "AB_ENV=production refuses to start without auth material: mutating endpoints would "
        "be open to anonymous callers. Set AB_API_TOKEN (write-scoped shared token), or "
        "AB_ADMIN_TOKEN (which issues the first write-scoped API key via /api/v1/keys), or "
        "provision an active write-scoped API key in the database. AB_ALLOW_INSECURE_PRODUCTION=true "
        "starts anyway and leaves mutations open. See docs/PRODUCTION.md."
    )


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(level=settings.log_level, log_format=settings.log_format)
    started_at = datetime.now(UTC)
    repository = ProjectRepository(
        settings.database_url,
        busy_timeout_ms=settings.sqlite_busy_timeout_ms,
        journal_mode=settings.sqlite_journal_mode,
        synchronous=settings.sqlite_synchronous,
        workspace_signing_key=settings.workspace_signing_key,
        pool_size=settings.db_pool_size,
    )
    if settings.is_production:
        _verify_production_storage(repository)
        _verify_production_auth(settings, repository)
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
    for header_name in ("X-AB-LLM-Provider", "X-AB-LLM-Token"):
        if header_name not in cors_headers:
            cors_headers.append(header_name)
    if settings.api_token or settings.readonly_api_token or settings.admin_token or repository.has_api_keys():
        for header_name in ("Authorization", "X-API-Key"):
            if header_name not in cors_headers:
                cors_headers.append(header_name)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        snapshot_service: SnapshotService | None = None
        snapshot_task: asyncio.Task[None] | None = None
        seed_enabled = settings.seed_demo_on_startup
        snapshot_repo = (os.getenv("AB_HF_SNAPSHOT_REPO") or "").strip()
        snapshot_token = (os.getenv("AB_HF_TOKEN") or "").strip()
        snapshot_interval_raw = (os.getenv("AB_HF_SNAPSHOT_INTERVAL_SECONDS") or "900").strip()
        try:
            snapshot_interval_seconds = max(0, int(snapshot_interval_raw))
        except ValueError:
            snapshot_interval_seconds = 900
            logger.warning(
                "snapshot: invalid interval %r, using default 900",
                snapshot_interval_raw,
            )

        log_event(
            logger,
            logging.INFO,
            "application started",
            event="startup",
            environment=settings.environment,
            version=settings.app_version,
            db_path=(
                redact_database_url(settings.database_url)
                if repository.backend_name == "postgres"
                else settings.db_path
            ),
            db_backend=repository.backend_name,
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

        if repository.supports_snapshots and snapshot_repo and snapshot_token:
            snapshot_service = SnapshotService(
                repo_id=snapshot_repo,
                local_db_path=Path(settings.db_path),
                hf_token=snapshot_token,
                app_version=settings.app_version,
                db_schema_version=repository.schema_version,
                workspace_schema_version=repository.workspace_schema_version,
            )
            restored = await snapshot_service.restore_latest()
            if restored:
                # Keep the demo seed enabled after a restore: seed_demo_workspace is
                # idempotent — it skips existing designs and any demo that already
                # carries exposures, and only tops up missing execution data or a
                # newly added demo on top of the restored snapshot. Snapshots that
                # predate the execution seed (Phase 5) would otherwise leave the
                # live-stats surface empty, so restoring must not disable the seed.
                logger.info(
                    "snapshot: restored from %s (demo seed tops up idempotently)",
                    snapshot_service.last_restored_commit or "unknown",
                )
            elif settings.seed_demo_on_startup:
                logger.info("snapshot: no snapshot available, falling back to seed")
        elif not repository.supports_snapshots:
            logger.info("snapshot: disabled for backend %s", repository.backend_name)
        else:
            logger.info("snapshot: disabled (env not set)")

        if seed_enabled:
            try:
                seed_demo_workspace(settings, repository)
            except Exception:
                logger.exception("demo-seed: failed")

        # Outbox worker starts once startup work (restore/seed) has settled; its
        # first pass also drains deliveries left claimable by a previous process.
        webhook_service.start_worker()

        if snapshot_service is not None and snapshot_interval_seconds > 0:
            async def run_snapshot_loop() -> None:
                while True:
                    await asyncio.sleep(snapshot_interval_seconds)
                    try:
                        await snapshot_service.push_snapshot()
                    except Exception:
                        logger.exception("snapshot: periodic push failed")

            snapshot_task = asyncio.create_task(run_snapshot_loop())
        yield
        if snapshot_task is not None:
            snapshot_task.cancel()
            try:
                await snapshot_task
            except asyncio.CancelledError:
                pass
        if snapshot_service is not None:
            try:
                await asyncio.wait_for(snapshot_service.push_snapshot(), timeout=10)
            except TimeoutError:
                logger.warning("snapshot: final push timed out")
            except Exception:
                logger.warning("snapshot: final push failed", exc_info=True)
        webhook_service.shutdown(wait=True)
        repository_close = getattr(repository, "close", None)
        if callable(repository_close):
            repository_close()

    app = FastAPI(
        title="AB Test Research Designer API",
        version=settings.app_version,
        description=(
            "Public API for deterministic A/B and multivariate experiment planning. "
            "It combines calculations, project storage, audit history, export flows, "
            "and optional local AI advice while preserving legacy shared-token access."
        ),
        contact={"name": "AB Test Research Designer"},
        license_info={"name": "MIT", "identifier": "MIT"},
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
            {"name": "slack", "description": "Slack App OAuth, slash commands, and interactive actions."},
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
    async def add_request_language(request: Request, call_next: RequestResponseEndpoint) -> Response:
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
    register_exception_handlers(app, logger=logger, settings=settings)
    # Intentional runtime injection seam: bind the report builder onto the routes
    # module dynamically. Kept as setattr so it stays opaque to mypy --strict
    # (no-implicit-reexport) — a direct assignment would couple to the import.
    setattr(analysis_routes, "build_experiment_report", build_experiment_report)  # noqa: B010
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
        create_execution_router(
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
    app.include_router(create_slack_router(settings, repository))
    app.include_router(create_system_router(settings, repository, runtime_counters, started_at))
    register_frontend_routes(app, settings)
    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("app.backend.app.main:app", host=settings.host, port=settings.port)
