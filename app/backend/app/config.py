import ipaddress
import os
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from app.backend.app.constants import DEFAULT_CORS_HEADERS, DEFAULT_CORS_METHODS

PRODUCTION_ENVIRONMENTS = frozenset({"production", "prod"})
POSTGRES_URL_SCHEMES = frozenset({"postgres", "postgresql"})
# Shared tokens (AB_API_TOKEN / AB_READONLY_API_TOKEN / AB_ADMIN_TOKEN) are bearer
# secrets: whoever holds one is the caller. 8 characters is a typo guard, not a
# strength floor — it stays for local/demo convenience, while production demands a
# length no one reaches by hand-picking a password.
MIN_SHARED_TOKEN_LENGTH = 8
PRODUCTION_MIN_SHARED_TOKEN_LENGTH = 24


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
    build_sha: str
    environment: str
    host: str
    port: int
    database_url: str
    db_pool_size: int
    db_path: str
    cors_origins: tuple[str, ...]
    cors_methods: tuple[str, ...]
    cors_headers: tuple[str, ...]
    frontend_dist_path: str
    serve_frontend_dist: bool
    llm_base_url: str
    llm_timeout_seconds: float
    llm_max_attempts: int
    llm_initial_backoff_seconds: float
    llm_backoff_multiplier: float
    mistral_api_key: str | None
    mistral_model: str
    sqlite_busy_timeout_ms: int
    sqlite_journal_mode: str
    sqlite_synchronous: str
    log_level: str
    log_format: str
    seed_demo_on_startup: bool
    public_demo: bool
    api_token: str | None
    readonly_api_token: str | None
    admin_token: str | None
    allow_insecure_production: bool
    workspace_signing_key: str | None
    slack_client_id: str | None
    slack_client_secret: str | None
    slack_signing_secret: str | None
    slack_review_channel: str | None
    rate_limit_enabled: bool
    rate_limit_requests: int
    rate_limit_window_seconds: int
    heavy_rate_limit_requests: int
    heavy_rate_limit_window_seconds: int
    auth_failure_limit: int
    auth_failure_window_seconds: int
    max_request_body_bytes: int
    max_workspace_body_bytes: int
    trusted_proxy_hops: int
    trusted_proxies: tuple[str, ...]
    # Retention windows in days (audit F-12). 0 disables automatic purge for that table.
    retention_exposures_days: int
    retention_conversions_days: int
    retention_audit_days: int
    retention_webhook_deliveries_days: int

    @property
    def is_production(self) -> bool:
        """True when AB_ENV declares a production environment (``production`` / ``prod``)."""
        return self.environment.strip().lower() in PRODUCTION_ENVIRONMENTS

    @property
    def uses_postgres(self) -> bool:
        """True when AB_DATABASE_URL points at PostgreSQL (the durable production backend)."""
        return urlparse(self.database_url).scheme in POSTGRES_URL_SCHEMES


def _read_csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    parsed = tuple(item.strip() for item in raw_value.split(",") if item.strip())
    return parsed or default


def _read_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _read_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _read_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _validate_settings(settings: Settings) -> Settings:
    allowed_journal_modes = {"DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"}
    allowed_synchronous_modes = {"OFF", "NORMAL", "FULL", "EXTRA"}
    allowed_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    allowed_log_formats = {"plain", "json"}

    if not settings.host.strip():
        raise ValueError("AB_HOST must not be empty")
    if not 1 <= settings.port <= 65535:
        raise ValueError("AB_PORT must be between 1 and 65535")
    if not settings.database_url.strip():
        raise ValueError("AB_DATABASE_URL must not be empty when configured")
    if settings.is_production and not settings.uses_postgres:
        raise ValueError(
            "AB_ENV=production requires a PostgreSQL AB_DATABASE_URL "
            "(postgres:// or postgresql://); the SQLite default is not durable for "
            "production. See docs/PRODUCTION.md."
        )
    if settings.db_pool_size < 1:
        raise ValueError("AB_DB_POOL_SIZE must be at least 1")
    if not settings.cors_origins:
        raise ValueError("AB_CORS_ORIGINS must contain at least one origin")
    if not settings.cors_methods:
        raise ValueError("AB_CORS_METHODS must contain at least one method")
    if not settings.cors_headers:
        raise ValueError("AB_CORS_HEADERS must contain at least one header")
    if not settings.db_path.strip():
        raise ValueError("AB_DB_PATH must not be empty")
    if settings.sqlite_busy_timeout_ms <= 0:
        raise ValueError("AB_SQLITE_BUSY_TIMEOUT_MS must be greater than 0")
    if settings.sqlite_journal_mode not in allowed_journal_modes:
        raise ValueError(
            "AB_SQLITE_JOURNAL_MODE must be one of DELETE, TRUNCATE, PERSIST, MEMORY, WAL, OFF"
        )
    if settings.sqlite_synchronous not in allowed_synchronous_modes:
        raise ValueError("AB_SQLITE_SYNCHRONOUS must be one of OFF, NORMAL, FULL, EXTRA")
    if settings.llm_timeout_seconds <= 0:
        raise ValueError("AB_LLM_TIMEOUT_SECONDS must be greater than 0")
    if settings.llm_max_attempts < 1:
        raise ValueError("AB_LLM_MAX_ATTEMPTS must be at least 1")
    if settings.llm_initial_backoff_seconds <= 0:
        raise ValueError("AB_LLM_INITIAL_BACKOFF_SECONDS must be greater than 0")
    if settings.llm_backoff_multiplier < 1:
        raise ValueError("AB_LLM_BACKOFF_MULTIPLIER must be at least 1")
    if settings.log_level not in allowed_log_levels:
        raise ValueError("AB_LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL")
    if settings.log_format not in allowed_log_formats:
        raise ValueError("AB_LOG_FORMAT must be one of plain, json")
    # Length policy is environment-dependent: production raises the floor so a
    # hand-typed "changeme1" cannot end up guarding a real deployment. The
    # non-production minimum is unchanged.
    min_token_length = PRODUCTION_MIN_SHARED_TOKEN_LENGTH if settings.is_production else MIN_SHARED_TOKEN_LENGTH
    for token_name, token_value in (
        ("AB_API_TOKEN", settings.api_token),
        ("AB_READONLY_API_TOKEN", settings.readonly_api_token),
        ("AB_ADMIN_TOKEN", settings.admin_token),
    ):
        if token_value is not None and len(token_value.strip()) < min_token_length:
            raise ValueError(f"{token_name} must be at least {min_token_length} characters when configured")
    if settings.workspace_signing_key is not None and len(settings.workspace_signing_key.strip()) < 16:
        raise ValueError("AB_WORKSPACE_SIGNING_KEY must be at least 16 characters when configured")
    if settings.rate_limit_requests < 1:
        raise ValueError("AB_RATE_LIMIT_REQUESTS must be at least 1")
    if settings.rate_limit_window_seconds < 1:
        raise ValueError("AB_RATE_LIMIT_WINDOW_SECONDS must be at least 1")
    if settings.heavy_rate_limit_requests < 1:
        raise ValueError("AB_HEAVY_RATE_LIMIT_REQUESTS must be at least 1")
    if settings.heavy_rate_limit_window_seconds < 1:
        raise ValueError("AB_HEAVY_RATE_LIMIT_WINDOW_SECONDS must be at least 1")
    if settings.auth_failure_limit < 1:
        raise ValueError("AB_AUTH_FAILURE_LIMIT must be at least 1")
    if settings.auth_failure_window_seconds < 1:
        raise ValueError("AB_AUTH_FAILURE_WINDOW_SECONDS must be at least 1")
    if settings.max_request_body_bytes < 1024:
        raise ValueError("AB_MAX_REQUEST_BODY_BYTES must be at least 1024")
    if settings.max_workspace_body_bytes < settings.max_request_body_bytes:
        raise ValueError("AB_MAX_WORKSPACE_BODY_BYTES must be greater than or equal to AB_MAX_REQUEST_BODY_BYTES")
    if settings.trusted_proxy_hops < 0:
        raise ValueError("AB_TRUSTED_PROXY_HOPS must be zero or greater")
    for proxy_entry in settings.trusted_proxies:
        try:
            ipaddress.ip_network(proxy_entry, strict=False)
        except ValueError as exc:
            raise ValueError(
                "AB_TRUSTED_PROXIES must be a comma-separated list of IP addresses or CIDR blocks"
            ) from exc
    if settings.trusted_proxies and settings.trusted_proxy_hops == 0:
        # Silently ignoring the allowlist would read as "proxy trust is configured"
        # while X-Forwarded-For stays unread. Fail fast instead.
        raise ValueError("AB_TRUSTED_PROXIES has no effect unless AB_TRUSTED_PROXY_HOPS is at least 1")
    for retention_name, retention_value in (
        ("AB_RETENTION_EXPOSURES_DAYS", settings.retention_exposures_days),
        ("AB_RETENTION_CONVERSIONS_DAYS", settings.retention_conversions_days),
        ("AB_RETENTION_AUDIT_DAYS", settings.retention_audit_days),
        ("AB_RETENTION_WEBHOOK_DELIVERIES_DAYS", settings.retention_webhook_deliveries_days),
    ):
        if retention_value < 0:
            raise ValueError(f"{retention_name} must be zero or greater")
    return settings


def _resolve_build_sha() -> str:
    # The semver alone cannot distinguish builds between releases (audit F-07):
    # images and CI stamp the exact commit via AB_BUILD_SHA; local runs fall back
    # to asking git so /health is honest in development too.
    env_value = (os.getenv("AB_BUILD_SHA") or "").strip()
    if env_value:
        return env_value
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no user input
            ["git", "rev-parse", "--short=12", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
            cwd=Path(__file__).resolve().parent,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    sha = completed.stdout.strip()
    if completed.returncode != 0 or not sha:
        return "unknown"
    return sha


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    default_db_path = Path(__file__).resolve().parents[1] / "data" / "projects.sqlite3"
    default_frontend_dist_path = Path(__file__).resolve().parents[3] / "app" / "frontend" / "dist"
    db_path = os.getenv("AB_DB_PATH", str(default_db_path))
    cors_origins = _read_csv_env(
        "AB_CORS_ORIGINS",
        ("http://127.0.0.1:5173", "http://localhost:5173"),
    )
    settings = Settings(
        app_name=os.getenv("AB_APP_NAME", "AB Test Research Designer API"),
        app_version=os.getenv("AB_APP_VERSION", "1.2.0"),
        build_sha=_resolve_build_sha(),
        environment=os.getenv("AB_ENV", "local"),
        host=os.getenv("AB_HOST", "127.0.0.1"),
        port=_read_int_env("AB_PORT", 8008),
        database_url=(os.getenv("AB_DATABASE_URL") or f"sqlite:///{Path(db_path).as_posix()}").strip(),
        db_pool_size=_read_int_env("AB_DB_POOL_SIZE", 10),
        db_path=db_path,
        cors_origins=cors_origins,
        cors_methods=_read_csv_env("AB_CORS_METHODS", DEFAULT_CORS_METHODS),
        cors_headers=_read_csv_env("AB_CORS_HEADERS", DEFAULT_CORS_HEADERS),
        frontend_dist_path=os.getenv("AB_FRONTEND_DIST_PATH", str(default_frontend_dist_path)),
        serve_frontend_dist=_read_bool_env("AB_SERVE_FRONTEND_DIST", True),
        llm_base_url=os.getenv("AB_LLM_BASE_URL", "http://localhost:8001"),
        llm_timeout_seconds=_read_float_env("AB_LLM_TIMEOUT_SECONDS", 60.0),
        llm_max_attempts=_read_int_env("AB_LLM_MAX_ATTEMPTS", 3),
        llm_initial_backoff_seconds=_read_float_env("AB_LLM_INITIAL_BACKOFF_SECONDS", 0.1),
        llm_backoff_multiplier=_read_float_env("AB_LLM_BACKOFF_MULTIPLIER", 2.0),
        mistral_api_key=(os.getenv("AB_MISTRAL_API_KEY") or "").strip() or None,
        mistral_model=os.getenv("AB_MISTRAL_MODEL", "mistral-small-latest").strip(),
        sqlite_busy_timeout_ms=_read_int_env("AB_SQLITE_BUSY_TIMEOUT_MS", 5000),
        sqlite_journal_mode=os.getenv("AB_SQLITE_JOURNAL_MODE", "WAL").strip().upper(),
        sqlite_synchronous=os.getenv("AB_SQLITE_SYNCHRONOUS", "NORMAL").strip().upper(),
        log_level=os.getenv("AB_LOG_LEVEL", "INFO").strip().upper(),
        log_format=os.getenv("AB_LOG_FORMAT", "plain").strip().lower(),
        seed_demo_on_startup=_read_bool_env("AB_SEED_DEMO_ON_STARTUP", False),
        public_demo=_read_bool_env("AB_PUBLIC_DEMO", False),
        api_token=(os.getenv("AB_API_TOKEN") or "").strip() or None,
        readonly_api_token=(os.getenv("AB_READONLY_API_TOKEN") or "").strip() or None,
        admin_token=(os.getenv("AB_ADMIN_TOKEN") or "").strip() or None,
        # Escape hatch for the production auth gate in main._verify_production_auth.
        # Default false: production must not accept writes without auth material.
        allow_insecure_production=_read_bool_env("AB_ALLOW_INSECURE_PRODUCTION", False),
        workspace_signing_key=(os.getenv("AB_WORKSPACE_SIGNING_KEY") or "").strip() or None,
        slack_client_id=(os.getenv("AB_SLACK_CLIENT_ID") or "").strip() or None,
        slack_client_secret=(os.getenv("AB_SLACK_CLIENT_SECRET") or "").strip() or None,
        slack_signing_secret=(os.getenv("AB_SLACK_SIGNING_SECRET") or "").strip() or None,
        slack_review_channel=(os.getenv("AB_SLACK_REVIEW_CHANNEL") or "").strip() or None,
        rate_limit_enabled=_read_bool_env("AB_RATE_LIMIT_ENABLED", True),
        rate_limit_requests=_read_int_env("AB_RATE_LIMIT_REQUESTS", 240),
        rate_limit_window_seconds=_read_int_env("AB_RATE_LIMIT_WINDOW_SECONDS", 60),
        # Simulation endpoints (see http_utils.HEAVY_COMPUTE_PATHS) burn far more
        # CPU per request than CRUD; the public demo exposes them anonymously, so
        # they get a tighter dedicated bucket on top of the global limit.
        heavy_rate_limit_requests=_read_int_env("AB_HEAVY_RATE_LIMIT_REQUESTS", 30),
        heavy_rate_limit_window_seconds=_read_int_env("AB_HEAVY_RATE_LIMIT_WINDOW_SECONDS", 60),
        auth_failure_limit=_read_int_env("AB_AUTH_FAILURE_LIMIT", 20),
        auth_failure_window_seconds=_read_int_env("AB_AUTH_FAILURE_WINDOW_SECONDS", 60),
        max_request_body_bytes=_read_int_env("AB_MAX_REQUEST_BODY_BYTES", 1_048_576),
        max_workspace_body_bytes=_read_int_env("AB_MAX_WORKSPACE_BODY_BYTES", 8_388_608),
        # 0 = never read X-Forwarded-For. Any other default would let an unproxied
        # deployment be rate-limit-bypassed by a forged header.
        trusted_proxy_hops=_read_int_env("AB_TRUSTED_PROXY_HOPS", 0),
        trusted_proxies=_read_csv_env("AB_TRUSTED_PROXIES", ()),
        retention_exposures_days=_read_int_env("AB_RETENTION_EXPOSURES_DAYS", 0),
        retention_conversions_days=_read_int_env("AB_RETENTION_CONVERSIONS_DAYS", 0),
        retention_audit_days=_read_int_env("AB_RETENTION_AUDIT_DAYS", 0),
        retention_webhook_deliveries_days=_read_int_env("AB_RETENTION_WEBHOOK_DELIVERIES_DAYS", 0),
    )
    return _validate_settings(settings)
