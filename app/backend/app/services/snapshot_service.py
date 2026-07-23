from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shutil
import sqlite3
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from huggingface_hub import CommitOperationAdd, HfApi
from huggingface_hub.errors import HfHubHTTPError

from app.backend.app.logging_utils import log_event

logger = logging.getLogger(__name__)


def create_consistent_sqlite_backup(source_path: Path, dest_path: Path) -> dict[str, Any]:
    """Stage a consistent SQLite copy that includes WAL-visible committed state.

    Uses the SQLite Online Backup API instead of copying the main DB file bytes.
    Metadata (sha256/size/user_version) is always derived from the staged file after
    the destination connection is closed.
    """
    source = Path(source_path)
    dest = Path(dest_path)
    if not source.exists():
        raise FileNotFoundError(f"source database missing: {source}")
    if dest.exists():
        dest.unlink()
    dest.parent.mkdir(parents=True, exist_ok=True)

    source_conn = sqlite3.connect(str(source), timeout=30.0)
    try:
        source_conn.execute("PRAGMA busy_timeout = 30000")
        dest_conn = sqlite3.connect(str(dest), timeout=30.0)
        try:
            source_conn.backup(dest_conn)
            quick_check = dest_conn.execute("PRAGMA quick_check").fetchone()[0]
            if quick_check != "ok":
                raise RuntimeError(f"staged snapshot failed quick_check: {quick_check}")
            user_version = int(dest_conn.execute("PRAGMA user_version").fetchone()[0])
        finally:
            dest_conn.close()
    finally:
        source_conn.close()

    size_bytes = dest.stat().st_size
    return {
        "path": dest,
        "sha256": _sha256_file(dest),
        "size_bytes": size_bytes,
        "user_version": user_version,
    }


def verify_sqlite_file(path: Path) -> dict[str, Any]:
    """Run PRAGMA quick_check and read user_version; raises on corruption."""
    connection = sqlite3.connect(str(path))
    try:
        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
        if quick_check != "ok":
            raise RuntimeError(f"sqlite quick_check failed: {quick_check}")
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        # Minimal smoke read so a post-restore migration failure surfaces as broken state.
        connection.execute("SELECT 1").fetchone()
    finally:
        connection.close()
    return {
        "path": path,
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
        "user_version": user_version,
    }


def remove_sqlite_sidecars(db_path: Path) -> None:
    """Drop WAL/SHM/journal sidecars so a replaced main file is not merged with stale state."""
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(f"{db_path}{suffix}")
        if sidecar.exists():
            try:
                sidecar.unlink()
            except OSError:
                logger.warning("snapshot: failed to remove sidecar %s", sidecar, exc_info=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SnapshotService:
    def __init__(
        self,
        repo_id: str,
        local_db_path: Path,
        hf_token: str | None,
        *,
        app_version: str = "unknown",
        db_schema_version: int | None = None,
        workspace_schema_version: int | None = None,
    ) -> None:
        self.repo_id = repo_id.strip()
        self.local_db_path = Path(local_db_path)
        self.hf_token = (hf_token or "").strip() or None
        # Three independent versions travel with a snapshot (audit F-07): the app
        # semver, the SQLite schema number and the workspace bundle format. The old
        # metadata wrote the semver into a field called schema_version, which was
        # neither the schema nor checked on restore.
        self.app_version = app_version
        self.db_schema_version = db_schema_version
        self.workspace_schema_version = workspace_schema_version
        self.last_restored_commit: str | None = None
        self.last_snapshot_sha256: str | None = None
        self.last_snapshot_size_bytes: int | None = None
        self.last_push_metrics: dict[str, Any] | None = None
        self.last_restore_metrics: dict[str, Any] | None = None

    @staticmethod
    def _sha256(path: Path) -> str:
        return _sha256_file(path)

    @staticmethod
    def _status_code(error: HfHubHTTPError) -> int | None:
        response = getattr(error, "response", None)
        if response is None:
            return None
        return getattr(response, "status_code", None)

    def _rollback_local_db(self, rollback_path: Path | None) -> None:
        """Replace the live DB with a pre-restore rollback copy (or remove if none)."""
        remove_sqlite_sidecars(self.local_db_path)
        if rollback_path is not None and rollback_path.exists():
            shutil.copyfile(rollback_path, self.local_db_path)
            remove_sqlite_sidecars(self.local_db_path)
            return
        if self.local_db_path.exists():
            self.local_db_path.unlink()

    async def restore_latest(
        self,
        *,
        post_replace: Callable[[], None] | None = None,
    ) -> bool:
        """Download the latest HF snapshot and replace the local DB.

        ``post_replace`` runs after the atomic file replace (typically schema
        re-bootstrap / migrate + any caller smoke checks). On failure the previous
        working DB is restored from a rollback copy taken before replace.
        """
        started = time.perf_counter()
        if not self.repo_id or not self.hf_token:
            return False

        api = HfApi(token=self.hf_token)
        try:
            repo_info = await asyncio.wait_for(
                asyncio.to_thread(
                    api.repo_info,
                    self.repo_id,
                    repo_type="dataset",
                    timeout=30,
                    token=self.hf_token,
                ),
                timeout=30,
            )
            revision = getattr(repo_info, "sha", None)
            if not revision:
                logger.warning("snapshot: restore refused, remote revision missing")
                return False

            # Bind both artifacts to one remote revision so metadata/db cannot
            # come from different commits under concurrent pushes.
            snapshot_path = Path(
                await asyncio.wait_for(
                    asyncio.to_thread(
                        api.hf_hub_download,
                        self.repo_id,
                        "projects.sqlite3",
                        repo_type="dataset",
                        token=self.hf_token,
                        revision=revision,
                        etag_timeout=30,
                        force_download=True,
                    ),
                    timeout=30,
                )
            )
            metadata_path = Path(
                await asyncio.wait_for(
                    asyncio.to_thread(
                        api.hf_hub_download,
                        self.repo_id,
                        "metadata.json",
                        repo_type="dataset",
                        token=self.hf_token,
                        revision=revision,
                        etag_timeout=30,
                        force_download=True,
                    ),
                    timeout=30,
                )
            )
        except TimeoutError:
            logger.warning("snapshot: restore timed out")
            self._record_restore_metrics(
                outcome="timeout",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            return False
        except HfHubHTTPError as error:
            status_code = self._status_code(error)
            if status_code in {401, 403}:
                logger.warning("snapshot: restore failed with status %s", status_code)
            elif status_code == 404:
                logger.info("snapshot: restore skipped, snapshot files not found")
            else:
                logger.warning("snapshot: restore failed", exc_info=True)
            self._record_restore_metrics(
                outcome="hub_error",
                duration_ms=int((time.perf_counter() - started) * 1000),
                status_code=status_code,
            )
            return False
        except Exception:
            logger.warning("snapshot: restore failed", exc_info=True)
            self._record_restore_metrics(
                outcome="error",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            return False

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("snapshot: restore failed to read metadata", exc_info=True)
            return False

        expected_sha256 = str(metadata.get("sha256") or "").strip()
        if not expected_sha256:
            logger.warning("snapshot: restore metadata missing sha256")
            return False

        # SQLite migrations only go forward: a snapshot written by a newer build
        # would leave this build running against a schema it does not understand.
        # Older metadata has no db_schema_version, so the guard skips it.
        snapshot_db_schema = metadata.get("db_schema_version")
        if (
            isinstance(snapshot_db_schema, int)
            and self.db_schema_version is not None
            and snapshot_db_schema > self.db_schema_version
        ):
            logger.warning(
                "snapshot: restore refused, snapshot db schema %s is newer than this build's %s",
                snapshot_db_schema,
                self.db_schema_version,
            )
            self._record_restore_metrics(
                outcome="refused_future_schema",
                duration_ms=int((time.perf_counter() - started) * 1000),
                db_schema_version=snapshot_db_schema,
            )
            return False

        actual_sha256 = self._sha256(snapshot_path)
        if actual_sha256 != expected_sha256:
            logger.warning("snapshot: restore sha mismatch")
            self._record_restore_metrics(
                outcome="sha_mismatch",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            return False

        self.local_db_path.parent.mkdir(parents=True, exist_ok=True)
        temp_snapshot_path: Path | None = None
        rollback_path: Path | None = None
        replaced = False
        try:
            if self.local_db_path.exists():
                with tempfile.NamedTemporaryFile(
                    dir=self.local_db_path.parent,
                    prefix=f"{self.local_db_path.stem}.rollback-",
                    suffix=self.local_db_path.suffix or ".sqlite3",
                    delete=False,
                ) as handle:
                    rollback_path = Path(handle.name)
                create_consistent_sqlite_backup(self.local_db_path, rollback_path)

            with tempfile.NamedTemporaryFile(
                dir=self.local_db_path.parent,
                prefix=f"{self.local_db_path.stem}.restore-",
                suffix=self.local_db_path.suffix or ".sqlite3",
                delete=False,
            ) as handle:
                temp_snapshot_path = Path(handle.name)
            shutil.copyfile(snapshot_path, temp_snapshot_path)
            # Integrity gate before replacing a working local DB.
            verify_sqlite_file(temp_snapshot_path)
            remove_sqlite_sidecars(self.local_db_path)
            temp_snapshot_path.replace(self.local_db_path)
            remove_sqlite_sidecars(self.local_db_path)
            replaced = True
            temp_snapshot_path = None  # ownership transferred to local path

            if post_replace is not None:
                post_replace()
            # Smoke after migrate/hook so a broken post-replace state never stays live.
            verify_sqlite_file(self.local_db_path)
        except Exception:
            if replaced:
                logger.warning(
                    "snapshot: restore rolled back after post-replace/smoke failure",
                    exc_info=True,
                )
                try:
                    self._rollback_local_db(rollback_path)
                except Exception:
                    logger.warning("snapshot: rollback restore failed", exc_info=True)
            else:
                if temp_snapshot_path is not None and temp_snapshot_path.exists():
                    temp_snapshot_path.unlink()
                logger.warning("snapshot: restore failed during local replace", exc_info=True)
            self._record_restore_metrics(
                outcome="rolled_back" if replaced else "replace_failed",
                duration_ms=int((time.perf_counter() - started) * 1000),
                revision=str(revision),
            )
            return False
        finally:
            if temp_snapshot_path is not None and temp_snapshot_path.exists():
                temp_snapshot_path.unlink()
            if rollback_path is not None and rollback_path.exists():
                rollback_path.unlink()

        self.last_restored_commit = revision
        self.last_snapshot_sha256 = expected_sha256
        size_bytes = metadata.get("size_bytes")
        self.last_snapshot_size_bytes = (
            int(size_bytes)
            if isinstance(size_bytes, int)
            else self.local_db_path.stat().st_size
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        self._record_restore_metrics(
            outcome="restored",
            duration_ms=duration_ms,
            revision=str(revision),
            sha256=expected_sha256[:12],
            size_bytes=self.last_snapshot_size_bytes,
            db_schema_version=snapshot_db_schema,
        )
        return True

    def _record_restore_metrics(self, **fields: Any) -> None:
        metrics = {"event": "snapshot_restore", **fields}
        self.last_restore_metrics = metrics
        log_event(
            logger,
            logging.INFO if fields.get("outcome") == "restored" else logging.WARNING,
            f"snapshot restore {fields.get('outcome', 'unknown')}",
            **metrics,
        )

    def _record_push_metrics(self, **fields: Any) -> None:
        metrics = {"event": "snapshot_push", **fields}
        self.last_push_metrics = metrics
        level = logging.INFO if fields.get("outcome") in {"pushed", "skipped_unchanged"} else logging.WARNING
        log_event(
            logger,
            level,
            f"snapshot push {fields.get('outcome', 'unknown')}",
            **metrics,
        )

    async def push_snapshot(self) -> str:
        started = time.perf_counter()
        if not self.repo_id or not self.hf_token:
            return ""
        if not self.local_db_path.exists():
            logger.warning("snapshot: push skipped, local db missing")
            self._record_push_metrics(
                outcome="skipped_missing_db",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            return ""

        timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        staged_path: Path | None = None
        metadata_path: Path | None = None
        api = HfApi(token=self.hf_token)
        sha256 = ""
        size_bytes = 0
        staged_user_version = 0
        delta_bytes = 0

        try:
            with tempfile.NamedTemporaryFile(
                dir=self.local_db_path.parent,
                prefix=f"{self.local_db_path.stem}.stage-",
                suffix=self.local_db_path.suffix or ".sqlite3",
                delete=False,
            ) as handle:
                staged_path = Path(handle.name)

            staged = await asyncio.wait_for(
                asyncio.to_thread(create_consistent_sqlite_backup, self.local_db_path, staged_path),
                timeout=60,
            )
            sha256 = str(staged["sha256"])
            size_bytes = int(staged["size_bytes"])
            staged_user_version = int(staged["user_version"])
            # Prefer the live staged PRAGMA; fall back to the configured constant
            # only when the DB has no user_version yet (brand-new empty file).
            metadata_db_schema = (
                staged_user_version
                if staged_user_version > 0
                else self.db_schema_version
            )

            if self.last_snapshot_sha256 is not None and sha256 == self.last_snapshot_sha256:
                duration_ms = int((time.perf_counter() - started) * 1000)
                logger.info(
                    "snapshot: skipped unchanged (sha256=%s, size=%sKB)",
                    sha256[:12],
                    size_bytes // 1024,
                )
                self._record_push_metrics(
                    outcome="skipped_unchanged",
                    duration_ms=duration_ms,
                    sha256=sha256[:12],
                    size_bytes=size_bytes,
                    user_version=staged_user_version,
                )
                return self.last_restored_commit or "unchanged"

            delta_bytes = (
                size_bytes
                if self.last_snapshot_size_bytes is None
                else abs(size_bytes - self.last_snapshot_size_bytes)
            )

            await asyncio.wait_for(
                asyncio.to_thread(
                    api.create_repo,
                    self.repo_id,
                    repo_type="dataset",
                    private=True,
                    exist_ok=True,
                    token=self.hf_token,
                ),
                timeout=30,
            )
            with tempfile.NamedTemporaryFile(
                "w",
                dir=self.local_db_path.parent,
                prefix=f"{self.local_db_path.stem}.snapshot-",
                suffix=".json",
                encoding="utf-8",
                delete=False,
            ) as handle:
                json.dump(
                    {
                        "app_version": self.app_version,
                        "db_schema_version": metadata_db_schema,
                        "workspace_schema_version": self.workspace_schema_version,
                        "ts": timestamp,
                        "sha256": sha256,
                        "size_bytes": size_bytes,
                    },
                    handle,
                )
                metadata_path = Path(handle.name)

            # One remote revision for DB + metadata — avoids partial remote state
            # when the second upload fails after the first succeeded.
            commit_info = await asyncio.wait_for(
                asyncio.to_thread(
                    api.create_commit,
                    self.repo_id,
                    operations=[
                        CommitOperationAdd(
                            path_in_repo="projects.sqlite3",
                            path_or_fileobj=str(staged_path),
                        ),
                        CommitOperationAdd(
                            path_in_repo="metadata.json",
                            path_or_fileobj=str(metadata_path),
                        ),
                    ],
                    commit_message=f"snapshot: {timestamp}",
                    repo_type="dataset",
                    token=self.hf_token,
                ),
                timeout=60,
            )
        except TimeoutError:
            logger.warning("snapshot: push timed out")
            self._record_push_metrics(
                outcome="timeout",
                duration_ms=int((time.perf_counter() - started) * 1000),
                sha256=sha256[:12] if sha256 else None,
                size_bytes=size_bytes or None,
            )
            return ""
        except HfHubHTTPError:
            logger.warning("snapshot: push failed", exc_info=True)
            self._record_push_metrics(
                outcome="hub_error",
                duration_ms=int((time.perf_counter() - started) * 1000),
                sha256=sha256[:12] if sha256 else None,
                size_bytes=size_bytes or None,
            )
            return ""
        except Exception:
            logger.warning("snapshot: push failed", exc_info=True)
            self._record_push_metrics(
                outcome="error",
                duration_ms=int((time.perf_counter() - started) * 1000),
                sha256=sha256[:12] if sha256 else None,
                size_bytes=size_bytes or None,
            )
            return ""
        finally:
            if metadata_path is not None and metadata_path.exists():
                metadata_path.unlink()
            if staged_path is not None and staged_path.exists():
                staged_path.unlink()

        commit_hash = str(getattr(commit_info, "oid", "") or "")
        self.last_snapshot_sha256 = sha256
        self.last_snapshot_size_bytes = size_bytes
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "snapshot: pushed %s (size=%sKB, delta=%sKB)",
            commit_hash or "unknown",
            size_bytes // 1024,
            delta_bytes // 1024,
        )
        self._record_push_metrics(
            outcome="pushed",
            duration_ms=duration_ms,
            commit=commit_hash or None,
            sha256=sha256[:12],
            size_bytes=size_bytes,
            delta_bytes=delta_bytes,
            user_version=staged_user_version,
        )
        return commit_hash
