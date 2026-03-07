from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
    environment: str
    host: str
    port: int
    db_path: str
    cors_origins: tuple[str, ...]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    default_db_path = Path(__file__).resolve().parents[1] / "data" / "projects.sqlite3"
    cors_origins = tuple(
        origin.strip()
        for origin in os.getenv(
            "AB_CORS_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173",
        ).split(",")
        if origin.strip()
    )
    return Settings(
        app_name=os.getenv("AB_APP_NAME", "AB Test Research Designer API"),
        app_version=os.getenv("AB_APP_VERSION", "0.1.0"),
        environment=os.getenv("AB_ENV", "local"),
        host=os.getenv("AB_HOST", "127.0.0.1"),
        port=int(os.getenv("AB_PORT", "8008")),
        db_path=os.getenv("AB_DB_PATH", str(default_db_path)),
        cors_origins=cors_origins,
    )
