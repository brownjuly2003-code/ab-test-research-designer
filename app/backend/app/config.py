from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path

from app.backend.app.constants import DEFAULT_CORS_HEADERS, DEFAULT_CORS_METHODS


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
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
    sqlite_busy_timeout_ms: int
    sqlite_journal_mode: str
    sqlite_synchronous: str
    log_level: str
    log_format: str
    seed_demo_on_startup: bool
    api_token: str | None
    readonly_api_token: str | None
    admin_token: str | None
    workspace_signing_key: str | None
    slack_client_id: str | None
    slack_client_secret: str | None
    slack_signing_secret: str | None
    slack_review_channel: str | None
    rate_limit_enabled: bool
    rate_limit_requests: int
    rate_limit_window_seconds: int
    auth_failure_limit: int
    auth_failure_window_seconds: int
    max_request_body_bytes: int
    max_workspace_body_bytes: int


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
    if settings.api_token is not None and len(settings.api_token.strip()) < 8:
        raise ValueError("AB_API_TOKEN must be at least 8 characters when configured")
    if settings.readonly_api_token is not None and len(settings.readonly_api_token.strip()) < 8:
        raise ValueError("AB_READONLY_API_TOKEN must be at least 8 characters when configured")
    if settings.admin_token is not None and len(settings.admin_token.strip()) < 8:
        raise ValueError("AB_ADMIN_TOKEN must be at least 8 characters when configured")
    if settings.workspace_signing_key is not None and len(settings.workspace_signing_key.strip()) < 16:
        raise ValueError("AB_WORKSPACE_SIGNING_KEY must be at least 16 characters when configured")
    if settings.rate_limit_requests < 1:
        raise ValueError("AB_RATE_LIMIT_REQUESTS must be at least 1")
    if settings.rate_limit_window_seconds < 1:
        raise ValueError("AB_RATE_LIMIT_WINDOW_SECONDS must be at least 1")
    if settings.auth_failure_limit < 1:
        raise ValueError("AB_AUTH_FAILURE_LIMIT must be at least 1")
    if settings.auth_failure_window_seconds < 1:
        raise ValueError("AB_AUTH_FAILURE_WINDOW_SECONDS must be at least 1")
    if settings.max_request_body_bytes < 1024:
        raise ValueError("AB_MAX_REQUEST_BODY_BYTES must be at least 1024")
    if settings.max_workspace_body_bytes < settings.max_request_body_bytes:
        raise ValueError("AB_MAX_WORKSPACE_BODY_BYTES must be greater than or equal to AB_MAX_REQUEST_BODY_BYTES")
    return settings


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
        app_version=os.getenv("AB_APP_VERSION", "1.1.0"),
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
        serve_frontend_dist=os.getenv("AB_SERVE_FRONTEND_DIST", "true").lower() not in {"0", "false", "no"},
        llm_base_url=os.getenv("AB_LLM_BASE_URL", "http://localhost:8001"),
        llm_timeout_seconds=_read_float_env("AB_LLM_TIMEOUT_SECONDS", 60.0),
        llm_max_attempts=_read_int_env("AB_LLM_MAX_ATTEMPTS", 3),
        llm_initial_backoff_seconds=_read_float_env("AB_LLM_INITIAL_BACKOFF_SECONDS", 0.1),
        llm_backoff_multiplier=_read_float_env("AB_LLM_BACKOFF_MULTIPLIER", 2.0),
        sqlite_busy_timeout_ms=_read_int_env("AB_SQLITE_BUSY_TIMEOUT_MS", 5000),
        sqlite_journal_mode=os.getenv("AB_SQLITE_JOURNAL_MODE", "WAL").strip().upper(),
        sqlite_synchronous=os.getenv("AB_SQLITE_SYNCHRONOUS", "NORMAL").strip().upper(),
        log_level=os.getenv("AB_LOG_LEVEL", "INFO").strip().upper(),
        log_format=os.getenv("AB_LOG_FORMAT", "plain").strip().lower(),
        seed_demo_on_startup=_read_bool_env("AB_SEED_DEMO_ON_STARTUP", False),
        api_token=(os.getenv("AB_API_TOKEN") or "").strip() or None,
        readonly_api_token=(os.getenv("AB_READONLY_API_TOKEN") or "").strip() or None,
        admin_token=(os.getenv("AB_ADMIN_TOKEN") or "").strip() or None,
        workspace_signing_key=(os.getenv("AB_WORKSPACE_SIGNING_KEY") or "").strip() or None,
        slack_client_id=(os.getenv("AB_SLACK_CLIENT_ID") or "").strip() or None,
        slack_client_secret=(os.getenv("AB_SLACK_CLIENT_SECRET") or "").strip() or None,
        slack_signing_secret=(os.getenv("AB_SLACK_SIGNING_SECRET") or "").strip() or None,
        slack_review_channel=(os.getenv("AB_SLACK_REVIEW_CHANNEL") or "").strip() or None,
        rate_limit_enabled=_read_bool_env("AB_RATE_LIMIT_ENABLED", True),
        rate_limit_requests=_read_int_env("AB_RATE_LIMIT_REQUESTS", 240),
        rate_limit_window_seconds=_read_int_env("AB_RATE_LIMIT_WINDOW_SECONDS", 60),
        auth_failure_limit=_read_int_env("AB_AUTH_FAILURE_LIMIT", 20),
        auth_failure_window_seconds=_read_int_env("AB_AUTH_FAILURE_WINDOW_SECONDS", 60),
        max_request_body_bytes=_read_int_env("AB_MAX_REQUEST_BODY_BYTES", 1_048_576),
        max_workspace_body_bytes=_read_int_env("AB_MAX_WORKSPACE_BODY_BYTES", 8_388_608),
    )
    return _validate_settings(settings)
