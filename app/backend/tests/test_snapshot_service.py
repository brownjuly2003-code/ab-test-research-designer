import asyncio
import hashlib
import json
import logging
import sqlite3
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.config import get_settings
from app.backend.app.main import create_app
from app.backend.app.repository import ProjectRepository
from app.backend.app.services.snapshot_service import (
    SnapshotService,
    create_consistent_sqlite_backup,
    verify_sqlite_file,
)


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


def _write_sqlite_db(path: Path, *, rows: list[tuple[str, ...]] | None = None, user_version: int = 14) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, v TEXT NOT NULL)")
        for (value,) in rows or [("seed",)]:
            connection.execute("INSERT INTO items(v) VALUES (?)", (value,))
        connection.execute(f"PRAGMA user_version = {int(user_version)}")
        connection.commit()
    finally:
        connection.close()


def _open_wal_db_with_pending_commit(path: Path) -> sqlite3.Connection:
    """Return an open connection where the latest commit is only in the WAL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, v TEXT NOT NULL)")
    connection.execute("INSERT INTO items(v) VALUES ('baseline')")
    connection.commit()
    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    connection.commit()
    connection.execute("INSERT INTO items(v) VALUES ('wal-only')")
    connection.commit()
    return connection


@pytest.fixture
def snapshot_service(tmp_path: Path) -> SnapshotService:
    return SnapshotService(
        repo_id="liovina/ab-test-designer-snapshots",
        local_db_path=tmp_path / "projects.sqlite3",
        hf_token="hf_test_token",
        app_version="1.1.0",
        db_schema_version=14,
        workspace_schema_version=3,
    )


@pytest.fixture
def app_env(monkeypatch, tmp_path: Path) -> Path:
    db_path = tmp_path / "app.sqlite3"
    monkeypatch.setenv("AB_DB_PATH", str(db_path))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    get_settings.cache_clear()
    yield db_path
    get_settings.cache_clear()


def test_create_consistent_sqlite_backup_includes_wal_committed_row(tmp_path: Path) -> None:
    db_path = tmp_path / "live.sqlite3"
    connection = _open_wal_db_with_pending_commit(db_path)
    try:
        wal_path = Path(f"{db_path}-wal")
        assert wal_path.exists() and wal_path.stat().st_size > 0

        # Main-file-only copy loses the WAL-only commit (audit F-01 reproduction).
        main_only = tmp_path / "main_only.sqlite3"
        main_only.write_bytes(db_path.read_bytes())
        main_conn = sqlite3.connect(main_only)
        try:
            assert [row[0] for row in main_conn.execute("SELECT v FROM items ORDER BY id")] == ["baseline"]
        finally:
            main_conn.close()

        staged = create_consistent_sqlite_backup(db_path, tmp_path / "staged.sqlite3")
        assert staged["user_version"] == 0  # unset in this fixture
        staged_conn = sqlite3.connect(staged["path"])
        try:
            values = [row[0] for row in staged_conn.execute("SELECT v FROM items ORDER BY id")]
        finally:
            staged_conn.close()
        assert values == ["baseline", "wal-only"]
        assert staged["sha256"] == _sha256(staged["path"])
        assert staged["size_bytes"] == staged["path"].stat().st_size
    finally:
        connection.close()


def test_create_consistent_sqlite_backup_under_concurrent_writer(tmp_path: Path) -> None:
    """Backup must stay integrity-clean and map to one transactional prefix under load."""
    db_path = tmp_path / "live.sqlite3"
    connection = sqlite3.connect(db_path, timeout=30.0)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, v TEXT NOT NULL)")
    connection.execute("INSERT INTO items(v) VALUES ('seed')")
    connection.commit()

    stop = threading.Event()
    errors: list[BaseException] = []
    writes_done = {"n": 0}

    def writer() -> None:
        writer_conn = sqlite3.connect(db_path, timeout=30.0)
        try:
            writer_conn.execute("PRAGMA busy_timeout = 30000")
            i = 0
            while not stop.is_set():
                i += 1
                writer_conn.execute("INSERT INTO items(v) VALUES (?)", (f"w-{i}",))
                writer_conn.commit()
                writes_done["n"] = i
                if i % 5 == 0:
                    time.sleep(0.001)
        except BaseException as exc:  # noqa: BLE001 — surface in main thread
            errors.append(exc)
        finally:
            writer_conn.close()

    thread = threading.Thread(target=writer, name="snapshot-concurrent-writer", daemon=True)
    thread.start()
    try:
        # Let the writer establish concurrent pressure before backup.
        deadline = time.monotonic() + 2.0
        while writes_done["n"] < 20 and time.monotonic() < deadline:
            time.sleep(0.005)
        assert writes_done["n"] >= 20, "writer did not produce enough commits"

        staged = create_consistent_sqlite_backup(db_path, tmp_path / "staged.sqlite3")
        verify_sqlite_file(staged["path"])
        staged_conn = sqlite3.connect(staged["path"])
        try:
            rows = [row[0] for row in staged_conn.execute("SELECT v FROM items ORDER BY id")]
            quick = staged_conn.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            staged_conn.close()
        assert quick == "ok"
        assert rows[0] == "seed"
        # Snapshot is a prefix of committed writes (single transactional point), not torn.
        assert all(value == "seed" or value.startswith("w-") for value in rows)
        committed_indexes = [int(value.split("-", 1)[1]) for value in rows if value.startswith("w-")]
        assert committed_indexes == list(range(1, len(committed_indexes) + 1))
        assert len(committed_indexes) >= 1
    finally:
        stop.set()
        thread.join(timeout=5)
        connection.close()
    assert not errors, f"writer errors: {errors}"


def test_verify_sqlite_file_rejects_corrupt_bytes(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.sqlite3"
    path.write_bytes(b"not-a-database")
    with pytest.raises((sqlite3.DatabaseError, sqlite3.OperationalError, RuntimeError)):
        verify_sqlite_file(path)


def test_restore_latest_replaces_local_db_on_valid_snapshot(snapshot_service: SnapshotService, tmp_path: Path) -> None:
    remote_db_path = tmp_path / "remote.sqlite3"
    _write_sqlite_db(remote_db_path, rows=[("remote",)], user_version=14)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "app_version": "1.1.0",
                "db_schema_version": 14,
                "workspace_schema_version": 3,
                "ts": "2026-04-23T12:34:56Z",
                "sha256": _sha256(remote_db_path),
                "size_bytes": remote_db_path.stat().st_size,
            }
        ),
        encoding="utf-8",
    )
    _write_sqlite_db(snapshot_service.local_db_path, rows=[("old",)], user_version=14)

    api = MagicMock()
    api.repo_info.return_value = SimpleNamespace(sha="restore-commit-123")
    download_kwargs: list[dict[str, object]] = []

    def hf_hub_download(repo_id, filename, **kwargs):
        download_kwargs.append({"filename": filename, **kwargs})
        return {
            "projects.sqlite3": str(remote_db_path),
            "metadata.json": str(metadata_path),
        }[filename]

    api.hf_hub_download.side_effect = hf_hub_download

    with patch("app.backend.app.services.snapshot_service.HfApi", return_value=api):
        restored = asyncio.run(snapshot_service.restore_latest())

    assert restored is True
    restored_conn = sqlite3.connect(snapshot_service.local_db_path)
    try:
        assert restored_conn.execute("SELECT v FROM items").fetchone()[0] == "remote"
    finally:
        restored_conn.close()
    assert snapshot_service.last_restored_commit == "restore-commit-123"
    assert all(item.get("revision") == "restore-commit-123" for item in download_kwargs)


def test_restore_latest_accepts_legacy_metadata_without_db_schema_version(
    snapshot_service: SnapshotService, tmp_path: Path
) -> None:
    # Snapshots pushed before the metadata split carry only the misnamed
    # semver field; they must keep restoring (the schema guard skips them).
    remote_db_path = tmp_path / "remote.sqlite3"
    _write_sqlite_db(remote_db_path, rows=[("remote",)], user_version=14)
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
    _write_sqlite_db(snapshot_service.local_db_path, rows=[("old",)], user_version=14)

    api = MagicMock()
    api.repo_info.return_value = SimpleNamespace(sha="restore-commit-legacy")
    api.hf_hub_download.side_effect = lambda repo_id, filename, **kwargs: {
        "projects.sqlite3": str(remote_db_path),
        "metadata.json": str(metadata_path),
    }[filename]

    with patch("app.backend.app.services.snapshot_service.HfApi", return_value=api):
        restored = asyncio.run(snapshot_service.restore_latest())

    assert restored is True
    restored_conn = sqlite3.connect(snapshot_service.local_db_path)
    try:
        assert restored_conn.execute("SELECT v FROM items").fetchone()[0] == "remote"
    finally:
        restored_conn.close()


def test_restore_latest_refuses_snapshot_from_newer_schema(
    snapshot_service: SnapshotService, tmp_path: Path, caplog
) -> None:
    remote_db_path = tmp_path / "remote.sqlite3"
    _write_sqlite_db(remote_db_path, rows=[("remote",)], user_version=17)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "app_version": "9.9.9",
                "db_schema_version": 17,
                "workspace_schema_version": 3,
                "ts": "2026-04-23T12:34:56Z",
                "sha256": _sha256(remote_db_path),
                "size_bytes": remote_db_path.stat().st_size,
            }
        ),
        encoding="utf-8",
    )
    _write_sqlite_db(snapshot_service.local_db_path, rows=[("old",)], user_version=14)

    api = MagicMock()
    api.repo_info.return_value = SimpleNamespace(sha="restore-commit-future")
    api.hf_hub_download.side_effect = lambda repo_id, filename, **kwargs: {
        "projects.sqlite3": str(remote_db_path),
        "metadata.json": str(metadata_path),
    }[filename]

    with patch("app.backend.app.services.snapshot_service.HfApi", return_value=api):
        with caplog.at_level(logging.WARNING):
            restored = asyncio.run(snapshot_service.restore_latest())

    assert restored is False
    old_conn = sqlite3.connect(snapshot_service.local_db_path)
    try:
        assert old_conn.execute("SELECT v FROM items").fetchone()[0] == "old"
    finally:
        old_conn.close()
    assert "newer than this build's" in caplog.text


def test_restore_latest_returns_false_on_sha_mismatch(snapshot_service: SnapshotService, tmp_path: Path) -> None:
    remote_db_path = tmp_path / "remote.sqlite3"
    _write_sqlite_db(remote_db_path, rows=[("remote",)], user_version=14)
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
    _write_sqlite_db(snapshot_service.local_db_path, rows=[("old",)], user_version=14)

    api = MagicMock()
    api.repo_info.return_value = SimpleNamespace(sha="restore-commit-123")
    api.hf_hub_download.side_effect = lambda repo_id, filename, **kwargs: {
        "projects.sqlite3": str(remote_db_path),
        "metadata.json": str(metadata_path),
    }[filename]

    with patch("app.backend.app.services.snapshot_service.HfApi", return_value=api):
        restored = asyncio.run(snapshot_service.restore_latest())

    assert restored is False
    old_conn = sqlite3.connect(snapshot_service.local_db_path)
    try:
        assert old_conn.execute("SELECT v FROM items").fetchone()[0] == "old"
    finally:
        old_conn.close()


def test_restore_latest_rolls_back_when_post_replace_fails(
    snapshot_service: SnapshotService, tmp_path: Path
) -> None:
    remote_db_path = tmp_path / "remote.sqlite3"
    _write_sqlite_db(remote_db_path, rows=[("remote",)], user_version=14)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "app_version": "1.1.0",
                "db_schema_version": 14,
                "workspace_schema_version": 3,
                "ts": "2026-04-23T12:34:56Z",
                "sha256": _sha256(remote_db_path),
                "size_bytes": remote_db_path.stat().st_size,
            }
        ),
        encoding="utf-8",
    )
    _write_sqlite_db(snapshot_service.local_db_path, rows=[("keep-me",)], user_version=14)

    api = MagicMock()
    api.repo_info.return_value = SimpleNamespace(sha="restore-commit-fail-hook")
    api.hf_hub_download.side_effect = lambda repo_id, filename, **kwargs: {
        "projects.sqlite3": str(remote_db_path),
        "metadata.json": str(metadata_path),
    }[filename]

    def boom() -> None:
        raise RuntimeError("migrate failed after replace")

    with patch("app.backend.app.services.snapshot_service.HfApi", return_value=api):
        restored = asyncio.run(snapshot_service.restore_latest(post_replace=boom))

    assert restored is False
    keep_conn = sqlite3.connect(snapshot_service.local_db_path)
    try:
        assert keep_conn.execute("SELECT v FROM items").fetchone()[0] == "keep-me"
    finally:
        keep_conn.close()
    assert snapshot_service.last_restored_commit is None
    assert snapshot_service.last_restore_metrics is not None
    assert snapshot_service.last_restore_metrics["outcome"] == "rolled_back"


def test_restore_latest_runs_post_replace_before_success(
    snapshot_service: SnapshotService, tmp_path: Path
) -> None:
    remote_db_path = tmp_path / "remote.sqlite3"
    _write_sqlite_db(remote_db_path, rows=[("remote",)], user_version=14)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "app_version": "1.1.0",
                "db_schema_version": 14,
                "workspace_schema_version": 3,
                "ts": "2026-04-23T12:34:56Z",
                "sha256": _sha256(remote_db_path),
                "size_bytes": remote_db_path.stat().st_size,
            }
        ),
        encoding="utf-8",
    )
    _write_sqlite_db(snapshot_service.local_db_path, rows=[("old",)], user_version=14)

    api = MagicMock()
    api.repo_info.return_value = SimpleNamespace(sha="restore-commit-hook-ok")
    api.hf_hub_download.side_effect = lambda repo_id, filename, **kwargs: {
        "projects.sqlite3": str(remote_db_path),
        "metadata.json": str(metadata_path),
    }[filename]
    seen: list[str] = []

    def mark() -> None:
        conn = sqlite3.connect(snapshot_service.local_db_path)
        try:
            seen.append(conn.execute("SELECT v FROM items").fetchone()[0])
        finally:
            conn.close()

    with patch("app.backend.app.services.snapshot_service.HfApi", return_value=api):
        restored = asyncio.run(snapshot_service.restore_latest(post_replace=mark))

    assert restored is True
    assert seen == ["remote"]
    assert snapshot_service.last_restore_metrics is not None
    assert snapshot_service.last_restore_metrics["outcome"] == "restored"


def test_restore_latest_refuses_corrupt_db_without_replacing_local(
    snapshot_service: SnapshotService, tmp_path: Path, caplog
) -> None:
    remote_db_path = tmp_path / "remote.sqlite3"
    # Valid header-less garbage that still has a matching sha in metadata.
    remote_db_path.write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "app_version": "1.1.0",
                "db_schema_version": 14,
                "workspace_schema_version": 3,
                "ts": "2026-04-23T12:34:56Z",
                "sha256": _sha256(remote_db_path),
                "size_bytes": remote_db_path.stat().st_size,
            }
        ),
        encoding="utf-8",
    )
    _write_sqlite_db(snapshot_service.local_db_path, rows=[("keep-me",)], user_version=14)

    api = MagicMock()
    api.repo_info.return_value = SimpleNamespace(sha="restore-commit-corrupt")
    api.hf_hub_download.side_effect = lambda repo_id, filename, **kwargs: {
        "projects.sqlite3": str(remote_db_path),
        "metadata.json": str(metadata_path),
    }[filename]

    with patch("app.backend.app.services.snapshot_service.HfApi", return_value=api):
        with caplog.at_level(logging.WARNING):
            restored = asyncio.run(snapshot_service.restore_latest())

    assert restored is False
    keep_conn = sqlite3.connect(snapshot_service.local_db_path)
    try:
        assert keep_conn.execute("SELECT v FROM items").fetchone()[0] == "keep-me"
    finally:
        keep_conn.close()
    assert "restore failed during local replace" in caplog.text


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


def test_push_snapshot_uploads_db_and_metadata_via_single_commit(
    snapshot_service: SnapshotService, tmp_path: Path
) -> None:
    _write_sqlite_db(snapshot_service.local_db_path, rows=[("snapshot-row",)], user_version=14)

    api = MagicMock()
    api.create_repo.return_value = "https://huggingface.co/datasets/liovina/ab-test-designer-snapshots"
    uploaded_metadata: dict[str, object] = {}
    staged_sha: list[str] = []
    staged_size: list[int] = []

    def create_commit_side_effect(repo_id, operations, **kwargs):
        assert len(operations) == 2
        path_by_repo = {op.path_in_repo: Path(op.path_or_fileobj) for op in operations}
        assert set(path_by_repo) == {"projects.sqlite3", "metadata.json"}
        db_path = path_by_repo["projects.sqlite3"]
        staged_sha.append(_sha256(db_path))
        staged_size.append(db_path.stat().st_size)
        uploaded_metadata.update(
            json.loads(path_by_repo["metadata.json"].read_text(encoding="utf-8"))
        )
        # Staged backup must include the committed row (not a raw main-file copy).
        staged_conn = sqlite3.connect(db_path)
        try:
            assert staged_conn.execute("SELECT v FROM items").fetchone()[0] == "snapshot-row"
            assert staged_conn.execute("PRAGMA user_version").fetchone()[0] == 14
        finally:
            staged_conn.close()
        return SimpleNamespace(oid="commit-123")

    api.create_commit.side_effect = create_commit_side_effect

    with patch("app.backend.app.services.snapshot_service.HfApi", return_value=api):
        commit_hash = asyncio.run(snapshot_service.push_snapshot())

    assert commit_hash == "commit-123"
    assert api.create_commit.call_count == 1
    assert api.upload_file.call_count == 0
    assert uploaded_metadata["app_version"] == "1.1.0"
    assert uploaded_metadata["db_schema_version"] == 14
    assert uploaded_metadata["workspace_schema_version"] == 3
    assert "schema_version" not in uploaded_metadata
    assert uploaded_metadata["sha256"] == staged_sha[0]
    assert uploaded_metadata["size_bytes"] == staged_size[0]


def test_push_snapshot_includes_wal_committed_row(snapshot_service: SnapshotService) -> None:
    connection = _open_wal_db_with_pending_commit(snapshot_service.local_db_path)
    try:
        api = MagicMock()
        api.create_repo.return_value = "ok"
        captured_rows: list[list[str]] = []

        def create_commit_side_effect(repo_id, operations, **kwargs):
            db_path = next(Path(op.path_or_fileobj) for op in operations if op.path_in_repo == "projects.sqlite3")
            staged = sqlite3.connect(db_path)
            try:
                captured_rows.append([row[0] for row in staged.execute("SELECT v FROM items ORDER BY id")])
            finally:
                staged.close()
            return SimpleNamespace(oid="wal-commit")

        api.create_commit.side_effect = create_commit_side_effect

        with patch("app.backend.app.services.snapshot_service.HfApi", return_value=api):
            commit_hash = asyncio.run(snapshot_service.push_snapshot())

        assert commit_hash == "wal-commit"
        assert captured_rows == [["baseline", "wal-only"]]
    finally:
        connection.close()


def test_push_snapshot_skips_unchanged_content(snapshot_service: SnapshotService) -> None:
    _write_sqlite_db(snapshot_service.local_db_path, rows=[("same",)], user_version=14)
    api = MagicMock()
    api.create_repo.return_value = "ok"
    api.create_commit.return_value = SimpleNamespace(oid="first")

    with patch("app.backend.app.services.snapshot_service.HfApi", return_value=api):
        first = asyncio.run(snapshot_service.push_snapshot())
        second = asyncio.run(snapshot_service.push_snapshot())

    assert first == "first"
    assert second in {"unchanged", "first"}
    assert api.create_commit.call_count == 1


def test_push_snapshot_returns_empty_string_on_hf_error(snapshot_service: SnapshotService, caplog) -> None:
    _write_sqlite_db(snapshot_service.local_db_path, rows=[("snapshot-row",)], user_version=14)

    api = MagicMock()
    api.create_repo.return_value = "https://huggingface.co/datasets/liovina/ab-test-designer-snapshots"
    api.create_commit.side_effect = _hub_error(500)

    with patch("app.backend.app.services.snapshot_service.HfApi", return_value=api):
        with caplog.at_level(logging.WARNING):
            commit_hash = asyncio.run(snapshot_service.push_snapshot())

    assert commit_hash == ""
    assert "snapshot: push failed" in caplog.text
    assert snapshot_service.last_push_metrics is not None
    assert snapshot_service.last_push_metrics["outcome"] == "hub_error"
    # Failed push must not claim a new snapshot identity.
    assert snapshot_service.last_snapshot_sha256 is None


def test_push_snapshot_create_commit_failure_preserves_previous_revision_for_restore(
    snapshot_service: SnapshotService, tmp_path: Path
) -> None:
    """Fault-injected mid-flight create_commit: remote stays on previous full revision."""
    previous_db = tmp_path / "previous.sqlite3"
    _write_sqlite_db(previous_db, rows=[("previous-good",)], user_version=14)
    previous_meta = tmp_path / "previous-meta.json"
    previous_sha = _sha256(previous_db)
    previous_meta.write_text(
        json.dumps(
            {
                "app_version": "1.1.0",
                "db_schema_version": 14,
                "workspace_schema_version": 3,
                "ts": "2026-04-23T10:00:00Z",
                "sha256": previous_sha,
                "size_bytes": previous_db.stat().st_size,
            }
        ),
        encoding="utf-8",
    )
    _write_sqlite_db(snapshot_service.local_db_path, rows=[("local-new",)], user_version=14)

    api = MagicMock()
    api.create_repo.return_value = "ok"
    api.create_commit.side_effect = _hub_error(503)
    # HEAD remains on the previous complete revision (single create_commit never partially applied).
    api.repo_info.return_value = SimpleNamespace(sha="previous-revision-sha")
    download_kwargs: list[dict[str, object]] = []

    def hf_hub_download(repo_id, filename, **kwargs):
        download_kwargs.append({"filename": filename, **kwargs})
        return {
            "projects.sqlite3": str(previous_db),
            "metadata.json": str(previous_meta),
        }[filename]

    api.hf_hub_download.side_effect = hf_hub_download

    with patch("app.backend.app.services.snapshot_service.HfApi", return_value=api):
        # Seed service memory as if a prior push succeeded.
        snapshot_service.last_snapshot_sha256 = previous_sha
        snapshot_service.last_snapshot_size_bytes = previous_db.stat().st_size
        snapshot_service.last_restored_commit = "previous-revision-sha"

        failed = asyncio.run(snapshot_service.push_snapshot())
        assert failed == ""
        # Local identity must stay on the last known good remote snapshot, not the failed stage.
        assert snapshot_service.last_snapshot_sha256 == previous_sha
        assert snapshot_service.last_push_metrics is not None
        assert snapshot_service.last_push_metrics["outcome"] == "hub_error"

        # Overwrite local with something else, then restore previous remote revision.
        _write_sqlite_db(snapshot_service.local_db_path, rows=[("after-failed-push",)], user_version=14)
        restored = asyncio.run(snapshot_service.restore_latest())

    assert restored is True
    restored_conn = sqlite3.connect(snapshot_service.local_db_path)
    try:
        assert restored_conn.execute("SELECT v FROM items").fetchone()[0] == "previous-good"
    finally:
        restored_conn.close()
    assert snapshot_service.last_restored_commit == "previous-revision-sha"
    assert all(item.get("revision") == "previous-revision-sha" for item in download_kwargs)
    assert api.create_commit.call_count == 1
    assert api.upload_file.call_count == 0


def test_reinitialize_after_restore_migrates_schema_n_minus_one(tmp_path: Path) -> None:
    db_path = tmp_path / "projects.sqlite3"
    # Minimal pre-bootstrap table plus old user_version; reinitialize must lift schema.
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                project_name TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_schema_version INTEGER NOT NULL DEFAULT 1,
                archived_at TEXT,
                last_analysis_json TEXT,
                last_analysis_at TEXT,
                last_analysis_run_id TEXT,
                last_exported_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO projects (
                id, project_name, payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("proj-1", "kept", "{}", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
    finally:
        connection.close()

    repository = ProjectRepository(f"sqlite:///{db_path.as_posix()}")
    # Constructor already migrates; force an older version again and re-run.
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("SELECT project_name FROM projects").fetchone()[0] == "kept"
    finally:
        connection.close()

    repository.reinitialize_after_restore()
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == repository.schema_version
        assert connection.execute("SELECT project_name FROM projects").fetchone()[0] == "kept"
    finally:
        connection.close()


def test_startup_restore_keeps_seed_for_topup_and_shutdown_pushes_snapshot(monkeypatch, app_env: Path, capsys) -> None:
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

    # A successful restore must NOT disable the demo seed: seed_demo_workspace is
    # idempotent and tops up execution data (and any newly added demo) on top of the
    # restored snapshot, so snapshots predating the execution seed (Phase 5) do not
    # leave the hosted demo's live-stats surface empty.
    seed_demo_workspace.assert_called_once()
    snapshot_service.restore_latest.assert_awaited_once()
    snapshot_service.push_snapshot.assert_awaited_once()
    assert "snapshot: restored from restore-commit-123 (demo seed tops up idempotently)" in capsys.readouterr().err


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


def test_create_app_passes_database_url_and_pool_size_to_repository(monkeypatch, app_env: Path) -> None:
    monkeypatch.setenv("AB_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/abtest")
    monkeypatch.setenv("AB_DB_POOL_SIZE", "12")
    monkeypatch.setenv("AB_SEED_DEMO_ON_STARTUP", "false")
    get_settings.cache_clear()

    repository = MagicMock()
    repository.has_api_keys.return_value = False
    repository.supports_snapshots = False

    with patch("app.backend.app.main.ProjectRepository", return_value=repository) as repository_cls:
        with patch("app.backend.app.main.WebhookService") as webhook_service_cls:
            webhook_service = webhook_service_cls.return_value
            webhook_service.shutdown.return_value = None

            with TestClient(create_app()):
                pass

    repository_cls.assert_called_once()
    assert repository_cls.call_args.args[0] == "postgresql://postgres:postgres@localhost:5432/abtest"
    assert repository_cls.call_args.kwargs["pool_size"] == 12


def test_startup_with_postgres_database_url_skips_snapshot_logic(monkeypatch, app_env: Path, capsys) -> None:
    monkeypatch.setenv("AB_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/abtest")
    monkeypatch.setenv("AB_SEED_DEMO_ON_STARTUP", "true")
    monkeypatch.setenv("AB_HF_SNAPSHOT_REPO", "liovina/ab-test-designer-snapshots")
    monkeypatch.setenv("AB_HF_TOKEN", "hf_test_token")
    get_settings.cache_clear()

    repository = MagicMock()
    repository.has_api_keys.return_value = False
    repository.supports_snapshots = False
    repository.backend_name = "postgres"

    with patch("app.backend.app.main.ProjectRepository", return_value=repository):
        with patch("app.backend.app.main.WebhookService") as webhook_service_cls:
            webhook_service = webhook_service_cls.return_value
            webhook_service.shutdown.return_value = None
            with patch("app.backend.app.main.SnapshotService") as snapshot_service_cls:
                with patch("app.backend.app.main.seed_demo_workspace") as seed_demo_workspace:
                    with TestClient(create_app()):
                        pass

    snapshot_service_cls.assert_not_called()
    seed_demo_workspace.assert_called_once()
    assert "snapshot: disabled for backend postgres" in capsys.readouterr().err
