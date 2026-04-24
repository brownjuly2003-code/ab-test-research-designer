from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.config import get_settings


def test_settings_reject_invalid_port(monkeypatch) -> None:
    monkeypatch.setenv("AB_PORT", "99999")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="AB_PORT must be between 1 and 65535"):
        get_settings()

    get_settings.cache_clear()


def test_settings_reject_invalid_llm_attempts(monkeypatch) -> None:
    monkeypatch.setenv("AB_LLM_MAX_ATTEMPTS", "0")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="AB_LLM_MAX_ATTEMPTS must be at least 1"):
        get_settings()

    get_settings.cache_clear()


def test_settings_reject_invalid_sqlite_journal_mode(monkeypatch) -> None:
    monkeypatch.setenv("AB_SQLITE_JOURNAL_MODE", "BROKEN")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="AB_SQLITE_JOURNAL_MODE must be one of"):
        get_settings()

    get_settings.cache_clear()


def test_settings_reject_invalid_log_format(monkeypatch) -> None:
    monkeypatch.setenv("AB_LOG_FORMAT", "yaml")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="AB_LOG_FORMAT must be one of plain, json"):
        get_settings()

    get_settings.cache_clear()


def test_settings_reject_too_short_api_token(monkeypatch) -> None:
    monkeypatch.setenv("AB_API_TOKEN", "short")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="AB_API_TOKEN must be at least 8 characters when configured"):
        get_settings()

    get_settings.cache_clear()


def test_settings_reject_too_short_readonly_api_token(monkeypatch) -> None:
    monkeypatch.setenv("AB_READONLY_API_TOKEN", "short")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="AB_READONLY_API_TOKEN must be at least 8 characters when configured"):
        get_settings()

    get_settings.cache_clear()


def test_settings_reject_too_short_admin_token(monkeypatch) -> None:
    monkeypatch.setenv("AB_ADMIN_TOKEN", "short")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="AB_ADMIN_TOKEN must be at least 8 characters when configured"):
        get_settings()

    get_settings.cache_clear()


def test_settings_reject_too_short_workspace_signing_key(monkeypatch) -> None:
    monkeypatch.setenv("AB_WORKSPACE_SIGNING_KEY", "too-short-key")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="AB_WORKSPACE_SIGNING_KEY must be at least 16 characters when configured"):
        get_settings()

    get_settings.cache_clear()


def test_settings_reject_invalid_rate_limit_toggle(monkeypatch) -> None:
    monkeypatch.setenv("AB_RATE_LIMIT_ENABLED", "sometimes")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="AB_RATE_LIMIT_ENABLED must be a boolean"):
        get_settings()

    get_settings.cache_clear()


def test_settings_reject_workspace_body_limit_smaller_than_general_limit(monkeypatch) -> None:
    monkeypatch.setenv("AB_MAX_REQUEST_BODY_BYTES", "4096")
    monkeypatch.setenv("AB_MAX_WORKSPACE_BODY_BYTES", "2048")
    get_settings.cache_clear()

    with pytest.raises(
        ValueError,
        match="AB_MAX_WORKSPACE_BODY_BYTES must be greater than or equal to AB_MAX_REQUEST_BODY_BYTES",
    ):
        get_settings()

    get_settings.cache_clear()


def test_settings_support_database_url_and_pool_size(monkeypatch) -> None:
    monkeypatch.setenv("AB_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/abtest")
    monkeypatch.setenv("AB_DB_POOL_SIZE", "12")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.database_url == "postgresql://postgres:postgres@localhost:5432/abtest"
    assert settings.db_pool_size == 12

    get_settings.cache_clear()
