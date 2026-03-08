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
