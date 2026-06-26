import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.main import _verify_production_storage


class _FakeRepository:
    """Duck-typed stand-in for ProjectRepository (no live database needed)."""

    def __init__(self, backend_name: str, summary: dict[str, Any]) -> None:
        self.backend_name = backend_name
        self._summary = summary

    def get_diagnostics_summary(self) -> dict[str, Any]:
        return self._summary


def test_verify_production_storage_passes_on_healthy_postgres() -> None:
    repo = _FakeRepository(
        "postgres",
        {"write_probe_ok": True, "write_probe_detail": "BEGIN succeeded"},
    )

    # Should not raise.
    _verify_production_storage(repo)


def test_verify_production_storage_rejects_non_postgres_backend() -> None:
    repo = _FakeRepository("sqlite", {"write_probe_ok": True})

    with pytest.raises(RuntimeError, match="requires the PostgreSQL backend"):
        _verify_production_storage(repo)


def test_verify_production_storage_rejects_failed_write_probe() -> None:
    repo = _FakeRepository(
        "postgres",
        {"write_probe_ok": False, "write_probe_detail": "connection refused"},
    )

    with pytest.raises(RuntimeError, match="connection refused"):
        _verify_production_storage(repo)
