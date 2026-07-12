from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel

from app.backend.app.http_utils import (
    AUTH_READ_ONLY_METHODS,
    get_auth_mode,
    resolve_client_identity,
)
from app.backend.app.redaction import mask_inline_credentials
from app.backend.app.schemas.api import (
    DiagnosticsAuthSummary,
    DiagnosticsFrontendSummary,
    DiagnosticsGuardsSummary,
    DiagnosticsLlmSummary,
    DiagnosticsLoggingSummary,
    DiagnosticsNetworkSummary,
    DiagnosticsResponse,
    DiagnosticsRuntimeSummary,
    DiagnosticsStorageSummary,
    ReadinessCheck,
    ReadinessResponse,
)

if TYPE_CHECKING:
    from app.backend.app.config import Settings
    from app.backend.app.repository import ProjectRepository


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    git_sha: str
    environment: str


def create_system_router(
    settings: "Settings",
    repository: "ProjectRepository",
    runtime_counters: dict[str, Any],
    start_time: datetime,
) -> APIRouter:
    router = APIRouter(tags=["system"])
    frontend_dist_path = Path(settings.frontend_dist_path)
    frontend_index_path = frontend_dist_path / "index.html"

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=settings.app_name,
            version=settings.app_version,
            git_sha=settings.build_sha,
            environment=settings.environment,
        )

    @router.get("/readyz", response_model=ReadinessResponse)
    def readyz(response: Response) -> ReadinessResponse:
        checks: list[ReadinessCheck] = []
        backend_name = getattr(repository, "backend_name", "sqlite")
        try:
            storage_summary = repository.get_diagnostics_summary()
            if backend_name == "postgres":
                checks.append(
                    ReadinessCheck(
                        name="postgres_storage",
                        ok=True,
                        detail="PostgreSQL reachable",
                    )
                )
                # storage_summary["schema_version"] is now READ from schema_migrations, so this
                # compares the database's actual version against the one this build requires.
                # It used to compare the code's constant with itself and could never fail.
                applied_schema_version = storage_summary["schema_version"]
                schema_current = applied_schema_version == repository.schema_version
                checks.append(
                    ReadinessCheck(
                        name="postgres_schema_version",
                        ok=schema_current,
                        detail=(
                            f"schema_version={applied_schema_version} expected={repository.schema_version}"
                            if schema_current
                            else (
                                f"schema_version={applied_schema_version} expected={repository.schema_version} — "
                                "pending migration: the database is not at the schema this build requires"
                            )
                        ),
                    )
                )
                checks.append(
                    ReadinessCheck(
                        name="postgres_write_probe",
                        ok=storage_summary["write_probe_ok"],
                        detail=storage_summary["write_probe_detail"],
                    )
                )
            else:
                checks.append(
                    ReadinessCheck(
                        name="sqlite_storage",
                        ok=True,
                        detail="SQLite reachable",
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
                    name=f"{backend_name}_storage",
                    ok=False,
                    # A driver error can quote the connection string it failed on.
                    detail=mask_inline_credentials(f"Storage diagnostics failed: {exc}"),
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
                    else ("Frontend dist present" if frontend_ready else "Frontend dist missing")
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
            generated_at=datetime.now(UTC).isoformat(),
            checks=checks,
        )

    @router.get("/api/v1/diagnostics", response_model=DiagnosticsResponse)
    def diagnostics(request: Request) -> DiagnosticsResponse:
        diagnostics_generated_at = datetime.now(UTC)
        storage_summary: dict[str, Any] = dict(repository.get_diagnostics_summary())
        api_keys_enabled = repository.has_api_keys()
        write_api_keys_enabled = repository.has_active_api_keys(scope="write")
        read_api_keys_enabled = repository.has_active_api_keys(scope="read")
        session_scope = getattr(request.state, "auth_scope", None)
        client_identity = resolve_client_identity(request, settings)

        auth_configured = (
            settings.api_token is not None
            or settings.readonly_api_token is not None
            or settings.admin_token is not None
            or api_keys_enabled
            or settings.public_demo
        )
        # Where the app stores its data, where it lives on disk and which networks it
        # trusts are operator facts, not health facts. A read-scope session — which on
        # the public demo is every anonymous visitor — gets none of them.
        #
        # The gate is the scope, not `admin_authenticated`: the admin token is only
        # recognised on the admin-only paths (`/api/v1/keys`, `/api/v1/webhooks`, see
        # http_runtime), so on this route it is never set. Whoever holds write scope
        # owns the installation; with no auth configured at all the only caller is the
        # owner on their own machine.
        operator_detail_visible = session_scope in {"write", "admin"} or not auth_configured
        if not operator_detail_visible:
            for operator_only_field in ("db_path", "db_parent_path", "disk_free_bytes"):
                storage_summary[operator_only_field] = None

        return DiagnosticsResponse(
            status="ok",
            generated_at=diagnostics_generated_at.isoformat(),
            started_at=start_time.isoformat(),
            uptime_seconds=round((diagnostics_generated_at - start_time).total_seconds(), 3),
            environment=settings.environment,
            app_version=settings.app_version,
            app_git_sha=settings.build_sha,
            request_timing_headers_enabled=True,
            storage=DiagnosticsStorageSummary.model_validate(storage_summary),
            frontend=DiagnosticsFrontendSummary(
                serve_frontend_dist=settings.serve_frontend_dist,
                dist_path=settings.frontend_dist_path if operator_detail_visible else None,
                dist_exists=frontend_dist_path.exists(),
            ),
            llm=DiagnosticsLlmSummary(
                provider="local_orchestrator",
                base_url=settings.llm_base_url if operator_detail_visible else None,
                timeout_seconds=settings.llm_timeout_seconds,
                max_attempts=settings.llm_max_attempts,
                initial_backoff_seconds=settings.llm_initial_backoff_seconds,
                backoff_multiplier=settings.llm_backoff_multiplier,
            ),
            logging=DiagnosticsLoggingSummary(
                level=settings.log_level,
                format=settings.log_format,
            ),
            auth=DiagnosticsAuthSummary(
                enabled=auth_configured,
                mode=get_auth_mode(settings.api_token, settings.readonly_api_token, api_keys_enabled),
                write_enabled=settings.api_token is not None or write_api_keys_enabled,
                readonly_enabled=settings.readonly_api_token is not None or read_api_keys_enabled,
                legacy_tokens_enabled=settings.api_token is not None or settings.readonly_api_token is not None,
                api_keys_enabled=api_keys_enabled,
                admin_token_enabled=settings.admin_token is not None,
                public_demo=settings.public_demo,
                session_scope=session_scope,
                session_source=getattr(request.state, "auth_source", None),
                session_can_write=session_scope in {"write", "admin"},
                session_admin_authenticated=bool(getattr(request.state, "admin_authenticated", False)),
                accepted_headers=["Authorization: Bearer", "X-API-Key"],
                read_only_methods=sorted(AUTH_READ_ONLY_METHODS),
            ),
            guards=DiagnosticsGuardsSummary(
                security_headers_enabled=True,
                rate_limit_enabled=settings.rate_limit_enabled,
                rate_limit_requests=settings.rate_limit_requests,
                rate_limit_window_seconds=settings.rate_limit_window_seconds,
                auth_failure_limit=settings.auth_failure_limit,
                auth_failure_window_seconds=settings.auth_failure_window_seconds,
                max_request_body_bytes=settings.max_request_body_bytes,
                max_workspace_body_bytes=settings.max_workspace_body_bytes,
            ),
            network=DiagnosticsNetworkSummary(
                direct_peer=client_identity.direct_peer,
                forwarded_for_chain=list(client_identity.forwarded_chain),
                trusted_proxy_hops=settings.trusted_proxy_hops,
                trusted_proxies=list(settings.trusted_proxies) if operator_detail_visible else None,
                resolved_client=client_identity.identifier,
                resolved_from=client_identity.source,
            ),
            runtime=DiagnosticsRuntimeSummary(**runtime_counters),
        )

    return router
