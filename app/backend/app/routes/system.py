from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.backend.app.http_utils import AUTH_READ_ONLY_METHODS, get_auth_mode
from app.backend.app.schemas.api import DiagnosticsResponse, ReadinessCheck, ReadinessResponse


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


def create_system_router(settings, repository, runtime_counters, start_time) -> APIRouter:
    router = APIRouter()
    frontend_dist_path = Path(settings.frontend_dist_path)
    frontend_index_path = frontend_dist_path / "index.html"

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=settings.app_name,
            version=settings.app_version,
            environment=settings.environment,
        )

    @router.get("/readyz", response_model=ReadinessResponse)
    def readyz(response: Response) -> ReadinessResponse:
        checks: list[ReadinessCheck] = []
        try:
            storage_summary = repository.get_diagnostics_summary()
            checks.append(
                ReadinessCheck(
                    name="sqlite_storage",
                    ok=True,
                    detail=f"Database path {storage_summary['db_path']}",
                )
            )
            checks.append(
                ReadinessCheck(
                    name="sqlite_schema_version",
                    ok=storage_summary["sqlite_user_version"] == repository.schema_version,
                    detail=(
                        f"user_version={storage_summary['sqlite_user_version']} expected={repository.schema_version}"
                    ),
                )
            )
            checks.append(
                ReadinessCheck(
                    name="sqlite_journal_mode",
                    ok=storage_summary["journal_mode"] == settings.sqlite_journal_mode,
                    detail=f"journal_mode={storage_summary['journal_mode']} expected={settings.sqlite_journal_mode}",
                )
            )
            checks.append(
                ReadinessCheck(
                    name="sqlite_write_probe",
                    ok=storage_summary["write_probe_ok"],
                    detail=storage_summary["write_probe_detail"],
                )
            )
        except Exception as exc:  # pragma: no cover - exercised via endpoint tests
            checks.append(
                ReadinessCheck(
                    name="sqlite_storage",
                    ok=False,
                    detail=f"Storage diagnostics failed: {exc}",
                )
            )
        frontend_ready = (not settings.serve_frontend_dist) or frontend_index_path.exists()
        checks.append(
            ReadinessCheck(
                name="frontend_dist",
                ok=frontend_ready,
                detail=(
                    "Frontend dist serving disabled"
                    if not settings.serve_frontend_dist
                    else f"Looking for {frontend_index_path}"
                ),
            )
        )
        checks.append(
            ReadinessCheck(
                name="llm_config",
                ok=True,
                detail=f"{settings.llm_max_attempts} attempt(s), timeout {settings.llm_timeout_seconds}s",
            )
        )
        checks.append(
            ReadinessCheck(
                name="logging_config",
                ok=True,
                detail=f"{settings.log_level} / {settings.log_format}",
            )
        )
        ready = all(check.ok for check in checks)
        response.status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            status="ready" if ready else "degraded",
            generated_at=datetime.now(timezone.utc).isoformat(),
            checks=checks,
        )

    @router.get("/api/v1/diagnostics", response_model=DiagnosticsResponse)
    def diagnostics() -> DiagnosticsResponse:
        diagnostics_generated_at = datetime.now(timezone.utc)
        storage_summary = repository.get_diagnostics_summary()
        return DiagnosticsResponse(
            status="ok",
            generated_at=diagnostics_generated_at.isoformat(),
            started_at=start_time.isoformat(),
            uptime_seconds=round((diagnostics_generated_at - start_time).total_seconds(), 3),
            environment=settings.environment,
            app_version=settings.app_version,
            request_timing_headers_enabled=True,
            storage=storage_summary,
            frontend={
                "serve_frontend_dist": settings.serve_frontend_dist,
                "dist_path": settings.frontend_dist_path,
                "dist_exists": frontend_dist_path.exists(),
            },
            llm={
                "provider": "local_orchestrator",
                "base_url": settings.llm_base_url,
                "timeout_seconds": settings.llm_timeout_seconds,
                "max_attempts": settings.llm_max_attempts,
                "initial_backoff_seconds": settings.llm_initial_backoff_seconds,
                "backoff_multiplier": settings.llm_backoff_multiplier,
            },
            logging={
                "level": settings.log_level,
                "format": settings.log_format,
            },
            auth={
                "enabled": settings.api_token is not None or settings.readonly_api_token is not None,
                "mode": get_auth_mode(settings.api_token, settings.readonly_api_token),
                "write_enabled": settings.api_token is not None,
                "readonly_enabled": settings.readonly_api_token is not None,
                "accepted_headers": ["Authorization: Bearer", "X-API-Key"],
                "read_only_methods": sorted(AUTH_READ_ONLY_METHODS),
            },
            guards={
                "security_headers_enabled": True,
                "rate_limit_enabled": settings.rate_limit_enabled,
                "rate_limit_requests": settings.rate_limit_requests,
                "rate_limit_window_seconds": settings.rate_limit_window_seconds,
                "auth_failure_limit": settings.auth_failure_limit,
                "auth_failure_window_seconds": settings.auth_failure_window_seconds,
                "max_request_body_bytes": settings.max_request_body_bytes,
                "max_workspace_body_bytes": settings.max_workspace_body_bytes,
            },
            runtime=runtime_counters,
        )

    return router
