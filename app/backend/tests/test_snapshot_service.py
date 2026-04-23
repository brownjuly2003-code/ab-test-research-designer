import asyncio
import hashlib
import json
import logging
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.config import get_settings
from app.backend.app.main import create_app
from app.backend.app.services.snapshot_service import SnapshotService


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hub_error(status_code: int) -> Exception:
    request = httpx.Request("GET", "https://huggingface.co/datasets/liovina/ab-test-designer-snapshots")
    response = httpx.Response(status_code, request=request)
    from huggingface_hub.errors import HfHubHTTPError

    return HfHubHTTPError(f"hub error: {status_code}", response=response)


@pytest.fixture
def snapshot_service(tmp_path: Path) -> SnapshotService:
    return SnapshotService(
        repo_id="liovina/ab-test-designer-snapshots",
        local_db_path=tmp_path / "projects.sqlite3",
        hf_token="hf_test_token",
    )


@pytest.fixture
def app_env(monkeypatch, tmp_path: Path) -> Path:
    db_path = tmp_path / "app.sqlite3"
    monkeypatch.setenv("AB_DB_PATH", str(db_path))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    get_settings.cache_clear()
    yield db_path
    get_settings.cache_clear()


def test_restore_latest_replaces_local_db_on_valid_snapshot(snapshot_service: SnapshotService, tmp_path: Path) -> None:
    remote_db_path = tmp_path / "remote.sqlite3"
    remote_db_path.write_bytes(b"remote-db")
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "schema_version": "1.1.0",
                "ts": "2026-04-23T12:34:56Z",
                "sha256": _sha256(remote_db_path),
                "size_bytes": remote_db_path.stat().st_size,
            }
        ),
        encoding="utf-8",
    )
    snapshot_service.local_db_path.write_bytes(b"old-db")

    api = MagicMock()
    api.repo_info.return_value = SimpleNamespace(sha="restore-commit-123")
    api.hf_hub_download.side_effect = lambda repo_id, filename, **kwargs: {
        "projects.sqlite3": str(remote_db_path),
        "metadata.json": str(metadata_path),
    }[filename]

    with patch("app.backend.app.services.snapshot_service.HfApi", return_value=api):
        restored = asyncio.run(snapshot_service.restore_latest())

    assert restored is True
    assert snapshot_service.local_db_path.read_bytes() == b"remote-db"
    assert snapshot_service.last_restored_commit == "restore-commit-123"


def test_restore_latest_returns_false_on_sha_mismatch(snapshot_service: SnapshotService, tmp_path: Path) -> None:
    remote_db_path = tmp_path / "remote.sqlite3"
    remote_db_path.write_bytes(b"remote-db")
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "schema_version": "1.1.0",
                "ts": "2026-04-23T12:34:56Z",
                "sha256": "deadbeef",
            }
        ),
        encoding="utf-8",
    )
    snapshot_service.local_db_path.write_bytes(b"old-db")

    api = MagicMock()
    api.repo_info.return_value = SimpleNamespace(sha="restore-commit-123")
    api.hf_hub_download.side_effect = lambda repo_id, filename, **kwargs: {
        "projects.sqlite3": str(remote_db_path),
        "metadata.json": str(metadata_path),
    }[filename]

    with patch("app.backend.app.services.snapshot_service.HfApi", return_value=api):
        restored = asyncio.run(snapshot_service.restore_latest())

    assert restored is False
    assert snapshot_service.local_db_path.read_bytes() == b"old-db"


def test_restore_latest_returns_false_on_missing_snapshot(snapshot_service: SnapshotService) -> None:
    api = MagicMock()
    api.repo_info.return_value = SimpleNamespace(sha="restore-commit-123")
    api.hf_hub_download.side_effect = _hub_error(404)

    with patch("app.backend.app.services.snapshot_service.HfApi", return_value=api):
        restored = asyncio.run(snapshot_service.restore_latest())

    assert restored is False
    assert not snapshot_service.local_db_path.exists()


def test_restore_latest_returns_false_on_unauthorized(snapshot_service: SnapshotService, caplog) -> None:
    api = MagicMock()
    api.repo_info.return_value = SimpleNamespace(sha="restore-commit-123")
    api.hf_hub_download.side_effect = _hub_error(401)

    with patch("app.backend.app.services.snapshot_service.HfApi", return_value=api):
        with caplog.at_level(logging.WARNING):
            restored = asyncio.run(snapshot_service.restore_latest())

    assert restored is False
    assert "snapshot: restore failed with status 401" in caplog.text


def test_push_snapshot_uploads_db_and_metadata(snapshot_service: SnapshotService) -> None:
    snapshot_service.local_db_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_service.local_db_path.write_bytes(b"snapshot-db")

    api = MagicMock()
    api.create_repo.return_value = "https://huggingface.co/datasets/liovina/ab-test-designer-snapshots"
    uploaded_metadata: dict[str, object] = {}

    def upload_file_side_effect(**kwargs):
        if kwargs["path_in_repo"] == "metadata.json":
            uploaded_metadata.update(
                json.loads(Path(kwargs["path_or_fileobj"]).read_text(encoding="utf-8"))
            )
        return SimpleNamespace(oid="commit-123")

    api.upload_file.side_effect = upload_file_side_effect

    with patch("app.backend.app.services.snapshot_service.HfApi", return_value=api):
        commit_hash = asyncio.run(snapshot_service.push_snapshot())

    assert commit_hash == "commit-123"
    assert api.upload_file.call_count == 2
    assert uploaded_metadata["schema_version"] == "1.1.0"
    assert uploaded_metadata["sha256"] == _sha256(snapshot_service.local_db_path)


def test_push_snapshot_returns_empty_string_on_hf_error(snapshot_service: SnapshotService, caplog) -> None:
    snapshot_service.local_db_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_service.local_db_path.write_bytes(b"snapshot-db")

    api = MagicMock()
    api.create_repo.return_value = "https://huggingface.co/datasets/liovina/ab-test-designer-snapshots"
    api.upload_file.side_effect = _hub_error(500)

    with patch("app.backend.app.services.snapshot_service.HfApi", return_value=api):
        with caplog.at_level(logging.WARNING):
            commit_hash = asyncio.run(snapshot_service.push_snapshot())

    assert commit_hash == ""
    assert "snapshot: push failed" in caplog.text


def test_startup_restore_skips_seed_and_shutdown_pushes_snapshot(monkeypatch, app_env: Path, capsys) -> None:
    monkeypatch.setenv("AB_SEED_DEMO_ON_STARTUP", "true")
    monkeypatch.setenv("AB_HF_SNAPSHOT_REPO", "liovina/ab-test-designer-snapshots")
    monkeypatch.setenv("AB_HF_TOKEN", "hf_test_token")
    monkeypatch.setenv("AB_HF_SNAPSHOT_INTERVAL_SECONDS", "0")
    get_settings.cache_clear()

    with patch("app.backend.app.main.SnapshotService") as snapshot_service_cls:
        with patch("app.backend.app.main.seed_demo_workspace") as seed_demo_workspace:
            snapshot_service = snapshot_service_cls.return_value
            snapshot_service.restore_latest = AsyncMock(return_value=True)
            snapshot_service.push_snapshot = AsyncMock(return_value="shutdown-commit")
            snapshot_service.last_restored_commit = "restore-commit-123"

            with TestClient(create_app()):
                pass

    seed_demo_workspace.assert_not_called()
    snapshot_service.restore_latest.assert_awaited_once()
    snapshot_service.push_snapshot.assert_awaited_once()
    assert "snapshot: restored from restore-commit-123" in capsys.readouterr().err


def test_startup_restore_falls_back_to_seed_when_snapshot_missing(monkeypatch, app_env: Path, capsys) -> None:
    monkeypatch.setenv("AB_SEED_DEMO_ON_STARTUP", "true")
    monkeypatch.setenv("AB_HF_SNAPSHOT_REPO", "liovina/ab-test-designer-snapshots")
    monkeypatch.setenv("AB_HF_TOKEN", "hf_test_token")
    monkeypatch.setenv("AB_HF_SNAPSHOT_INTERVAL_SECONDS", "0")
    get_settings.cache_clear()

    with patch("app.backend.app.main.SnapshotService") as snapshot_service_cls:
        with patch("app.backend.app.main.seed_demo_workspace") as seed_demo_workspace:
            snapshot_service = snapshot_service_cls.return_value
            snapshot_service.restore_latest = AsyncMock(return_value=False)
            snapshot_service.push_snapshot = AsyncMock(return_value="shutdown-commit")
            snapshot_service.last_restored_commit = None

            with TestClient(create_app()):
                pass

    seed_demo_workspace.assert_called_once()
    snapshot_service.restore_latest.assert_awaited_once()
    snapshot_service.push_snapshot.assert_awaited_once()
    assert "snapshot: no snapshot available, falling back to seed" in capsys.readouterr().err


def test_startup_without_snapshot_env_skips_snapshot_logic(monkeypatch, app_env: Path, capsys) -> None:
    monkeypatch.delenv("AB_HF_SNAPSHOT_REPO", raising=False)
    monkeypatch.delenv("AB_HF_TOKEN", raising=False)
    monkeypatch.setenv("AB_SEED_DEMO_ON_STARTUP", "false")
    get_settings.cache_clear()

    with patch("app.backend.app.main.SnapshotService") as snapshot_service_cls:
        with TestClient(create_app()):
            pass

    snapshot_service_cls.assert_not_called()
    assert "snapshot: disabled (env not set)" in capsys.readouterr().err
