"""Diagnostics and readiness payloads."""

from typing import Literal

from pydantic import BaseModel


class DiagnosticsStorageSummary(BaseModel):
    # Operator-only fields. A read-scope session (which on the public demo is every
    # anonymous caller) gets None: the storage location and the host's free disk say
    # nothing about the app's health and everything about where it runs.
    db_path: str | None = None
    db_parent_path: str | None = None
    disk_free_bytes: int | None = None
    db_exists: bool
    db_size_bytes: int
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
    dist_path: str | None = None  # operator-only: absolute filesystem path
    dist_exists: bool


class DiagnosticsLlmSummary(BaseModel):
    provider: str
    base_url: str | None = None  # operator-only: internal network address
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
    max_slack_body_bytes: int = 65_536
    slack_rate_limit_requests: int = 60
    compute_admission_enabled: bool = True
    compute_max_heavy_concurrent: int = 2


class DiagnosticsNetworkSummary(BaseModel):
    """The server-side view of the calling request's addressing.

    Echoes back what the app received for THIS request: the direct socket peer,
    the parsed `X-Forwarded-For` chain, and which of the two the rate limiter
    resolved as the caller under the configured trust. Send a marker header and
    everything to its right in `forwarded_for_chain` was appended by real
    proxies — that count is the correct `AB_TRUSTED_PROXY_HOPS` value.
    """

    direct_peer: str | None
    forwarded_for_chain: list[str]
    trusted_proxy_hops: int
    trusted_proxies: list[str] | None = None  # operator-only: the configured CIDR allowlist
    resolved_client: str
    resolved_from: Literal["forwarded_header", "direct_peer"]


class DiagnosticsRuntimeSummary(BaseModel):
    total_requests: int
    success_responses: int
    client_error_responses: int
    server_error_responses: int
    auth_rejections: int
    rate_limited_responses: int = 0
    request_body_rejections: int = 0
    compute_capacity_rejections: int = 0
    last_request_at: str | None = None
    last_error_at: str | None = None
    last_error_code: str | None = None
    # RED-style latency (process-local, audit F-12). Avg/max are None until the
    # first completed request has been timed.
    process_time_ms_count: int = 0
    process_time_ms_avg: float | None = None
    process_time_ms_max: float | None = None
    error_rate: float = 0.0


class DiagnosticsWebhooksSummary(BaseModel):
    """Outbox visibility (audit F-09): queue depth per status and how stale the
    queue head is. A growing oldest_due_age_seconds means the worker is stuck."""

    pending: int
    retrying: int
    delivered: int
    failed: int
    oldest_due_age_seconds: float | None = None


class DiagnosticsTopologySummary(BaseModel):
    """Supported deployment topology (audit F-12).

    The runtime is a **single-instance** process: rate limits, auth-failure
    throttles, and RED counters live in process memory. Multiple replicas would
    fragment those controls — use a shared edge gateway/Redis if you need them
    to be global. The durable data plane (SQLite file or PostgreSQL + webhook
    outbox leases) can still be externalised independently of this process scope.
    """

    supported: Literal["single_instance"] = "single_instance"
    rate_limit_state: Literal["in_process"] = "in_process"
    runtime_counters_scope: Literal["process"] = "process"
    notes: str = (
        "Rate limits, auth-failure throttles, and request counters are per-process. "
        "Do not run multiple app replicas without an edge/shared rate limiter."
    )


class DiagnosticsRetentionSummary(BaseModel):
    """Configured retention windows (days). ``0`` means automatic purge is off."""

    exposures_days: int = 0
    conversions_days: int = 0
    audit_days: int = 0
    webhook_deliveries_days: int = 0
    auto_purge_enabled: bool = False
    notes: str = (
        "Automatic purge is opt-in via AB_RETENTION_*_DAYS. Operators can also call "
        "POST /api/v1/admin/retention/purge. IP addresses and user ids may be personal "
        "data — size retention windows to your DSR/policy needs."
    )


class DiagnosticsResponse(BaseModel):
    status: str
    generated_at: str
    started_at: str
    uptime_seconds: float
    environment: str
    app_version: str
    app_git_sha: str
    request_timing_headers_enabled: bool
    storage: DiagnosticsStorageSummary
    frontend: DiagnosticsFrontendSummary
    llm: DiagnosticsLlmSummary
    logging: DiagnosticsLoggingSummary
    auth: DiagnosticsAuthSummary
    guards: DiagnosticsGuardsSummary
    network: DiagnosticsNetworkSummary
    runtime: DiagnosticsRuntimeSummary
    webhooks: DiagnosticsWebhooksSummary
    topology: DiagnosticsTopologySummary
    retention: DiagnosticsRetentionSummary


class ReadinessCheck(BaseModel):
    name: str
    ok: bool
    detail: str


class ReadinessResponse(BaseModel):
    status: str
    generated_at: str
    checks: list[ReadinessCheck]
