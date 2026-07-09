"""Diagnostics and readiness payloads."""

from typing import Literal

from pydantic import BaseModel


class DiagnosticsStorageSummary(BaseModel):
    db_path: str
    db_parent_path: str
    db_exists: bool
    db_size_bytes: int
    disk_free_bytes: int
    schema_version: int
    sqlite_user_version: int
    busy_timeout_ms: int
    journal_mode: str
    synchronous: str
    write_probe_ok: bool
    write_probe_detail: str
    projects_total: int
    archived_projects_total: int
    analysis_runs_total: int
    export_events_total: int
    project_revisions_total: int
    workspace_bundle_schema_version: int
    workspace_signature_enabled: bool
    latest_project_updated_at: str | None = None


class DiagnosticsFrontendSummary(BaseModel):
    serve_frontend_dist: bool
    dist_path: str
    dist_exists: bool


class DiagnosticsLlmSummary(BaseModel):
    provider: str
    base_url: str
    timeout_seconds: float
    max_attempts: int
    initial_backoff_seconds: float
    backoff_multiplier: float


class DiagnosticsLoggingSummary(BaseModel):
    level: str
    format: str


class DiagnosticsAuthSummary(BaseModel):
    enabled: bool
    mode: str
    write_enabled: bool
    readonly_enabled: bool
    legacy_tokens_enabled: bool = False
    api_keys_enabled: bool = False
    admin_token_enabled: bool = False
    public_demo: bool = False
    session_scope: Literal["read", "write", "admin"] | None = None
    session_source: Literal["legacy", "api_key", "admin_token", "anonymous"] | None = None
    session_can_write: bool = False
    session_admin_authenticated: bool = False
    accepted_headers: list[str]
    read_only_methods: list[str]


class DiagnosticsGuardsSummary(BaseModel):
    security_headers_enabled: bool
    rate_limit_enabled: bool
    rate_limit_requests: int
    rate_limit_window_seconds: int
    auth_failure_limit: int
    auth_failure_window_seconds: int
    max_request_body_bytes: int
    max_workspace_body_bytes: int


class DiagnosticsRuntimeSummary(BaseModel):
    total_requests: int
    success_responses: int
    client_error_responses: int
    server_error_responses: int
    auth_rejections: int
    rate_limited_responses: int = 0
    request_body_rejections: int = 0
    last_request_at: str | None = None
    last_error_at: str | None = None
    last_error_code: str | None = None


class DiagnosticsResponse(BaseModel):
    status: str
    generated_at: str
    started_at: str
    uptime_seconds: float
    environment: str
    app_version: str
    request_timing_headers_enabled: bool
    storage: DiagnosticsStorageSummary
    frontend: DiagnosticsFrontendSummary
    llm: DiagnosticsLlmSummary
    logging: DiagnosticsLoggingSummary
    auth: DiagnosticsAuthSummary
    guards: DiagnosticsGuardsSummary
    runtime: DiagnosticsRuntimeSummary


class ReadinessCheck(BaseModel):
    name: str
    ok: bool
    detail: str


class ReadinessResponse(BaseModel):
    status: str
    generated_at: str
    checks: list[ReadinessCheck]
