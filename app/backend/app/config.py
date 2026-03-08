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


def _read_csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    parsed = tuple(item.strip() for item in raw_value.split(",") if item.strip())
    return parsed or default


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    default_db_path = Path(__file__).resolve().parents[1] / "data" / "projects.sqlite3"
    default_frontend_dist_path = Path(__file__).resolve().parents[3] / "app" / "frontend" / "dist"
    cors_origins = _read_csv_env(
        "AB_CORS_ORIGINS",
        ("http://127.0.0.1:5173", "http://localhost:5173"),
    )
    return Settings(
        app_name=os.getenv("AB_APP_NAME", "AB Test Research Designer API"),
        app_version=os.getenv("AB_APP_VERSION", "0.1.0"),
        environment=os.getenv("AB_ENV", "local"),
        host=os.getenv("AB_HOST", "127.0.0.1"),
        port=int(os.getenv("AB_PORT", "8008")),
        db_path=os.getenv("AB_DB_PATH", str(default_db_path)),
        cors_origins=cors_origins,
        cors_methods=_read_csv_env("AB_CORS_METHODS", DEFAULT_CORS_METHODS),
        cors_headers=_read_csv_env("AB_CORS_HEADERS", DEFAULT_CORS_HEADERS),
        frontend_dist_path=os.getenv("AB_FRONTEND_DIST_PATH", str(default_frontend_dist_path)),
        serve_frontend_dist=os.getenv("AB_SERVE_FRONTEND_DIST", "true").lower() not in {"0", "false", "no"},
        llm_base_url=os.getenv("AB_LLM_BASE_URL", "http://localhost:8001"),
        llm_timeout_seconds=float(os.getenv("AB_LLM_TIMEOUT_SECONDS", "60")),
        llm_max_attempts=int(os.getenv("AB_LLM_MAX_ATTEMPTS", "3")),
        llm_initial_backoff_seconds=float(os.getenv("AB_LLM_INITIAL_BACKOFF_SECONDS", "0.1")),
        llm_backoff_multiplier=float(os.getenv("AB_LLM_BACKOFF_MULTIPLIER", "2")),
    )
