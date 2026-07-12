from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from huggingface_hub import HfApi
from huggingface_hub.errors import HfHubHTTPError

logger = logging.getLogger(__name__)


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

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _status_code(error: HfHubHTTPError) -> int | None:
        response = getattr(error, "response", None)
        if response is None:
            return None
        return getattr(response, "status_code", None)

    async def restore_latest(self) -> bool:
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
            snapshot_path = Path(
                await asyncio.wait_for(
                    asyncio.to_thread(
                        api.hf_hub_download,
                        self.repo_id,
                        "projects.sqlite3",
                        repo_type="dataset",
                        token=self.hf_token,
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
                        etag_timeout=30,
                        force_download=True,
                    ),
                    timeout=30,
                )
            )
        except TimeoutError:
            logger.warning("snapshot: restore timed out")
            return False
        except HfHubHTTPError as error:
            status_code = self._status_code(error)
            if status_code in {401, 403}:
                logger.warning("snapshot: restore failed with status %s", status_code)
            elif status_code == 404:
                logger.info("snapshot: restore skipped, snapshot files not found")
            else:
                logger.warning("snapshot: restore failed", exc_info=True)
            return False
        except Exception:
            logger.warning("snapshot: restore failed", exc_info=True)
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
            return False

        actual_sha256 = self._sha256(snapshot_path)
        if actual_sha256 != expected_sha256:
            logger.warning("snapshot: restore sha mismatch")
            return False

        self.local_db_path.parent.mkdir(parents=True, exist_ok=True)
        temp_snapshot_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.local_db_path.parent,
                prefix=f"{self.local_db_path.stem}.restore-",
                suffix=self.local_db_path.suffix or ".sqlite3",
                delete=False,
            ) as handle:
                temp_snapshot_path = Path(handle.name)
            shutil.copyfile(snapshot_path, temp_snapshot_path)
            temp_snapshot_path.replace(self.local_db_path)
        except Exception:
            if temp_snapshot_path is not None and temp_snapshot_path.exists():
                temp_snapshot_path.unlink()
            logger.warning("snapshot: restore failed during local replace", exc_info=True)
            return False

        self.last_restored_commit = getattr(repo_info, "sha", None)
        self.last_snapshot_sha256 = expected_sha256
        size_bytes = metadata.get("size_bytes")
        self.last_snapshot_size_bytes = (
            int(size_bytes)
            if isinstance(size_bytes, int)
            else self.local_db_path.stat().st_size
        )
        return True

    async def push_snapshot(self) -> str:
        if not self.repo_id or not self.hf_token:
            return ""
        if not self.local_db_path.exists():
            logger.warning("snapshot: push skipped, local db missing")
            return ""

        timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        sha256 = self._sha256(self.local_db_path)
        size_bytes = self.local_db_path.stat().st_size
        delta_bytes = (
            size_bytes
            if self.last_snapshot_size_bytes is None
            else abs(size_bytes - self.last_snapshot_size_bytes)
        )
        metadata_path: Path | None = None
        api = HfApi(token=self.hf_token)

        try:
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
                        "db_schema_version": self.db_schema_version,
                        "workspace_schema_version": self.workspace_schema_version,
                        "ts": timestamp,
                        "sha256": sha256,
                        "size_bytes": size_bytes,
                    },
                    handle,
                )
                metadata_path = Path(handle.name)
            await asyncio.wait_for(
                asyncio.to_thread(
                    api.upload_file,
                    path_or_fileobj=self.local_db_path,
                    path_in_repo="projects.sqlite3",
                    repo_id=self.repo_id,
                    repo_type="dataset",
                    token=self.hf_token,
                    commit_message=f"snapshot: {timestamp}",
                ),
                timeout=30,
            )
            commit_info = await asyncio.wait_for(
                asyncio.to_thread(
                    api.upload_file,
                    path_or_fileobj=metadata_path,
                    path_in_repo="metadata.json",
                    repo_id=self.repo_id,
                    repo_type="dataset",
                    token=self.hf_token,
                    commit_message=f"snapshot: {timestamp}",
                ),
                timeout=30,
            )
        except TimeoutError:
            logger.warning("snapshot: push timed out")
            return ""
        except HfHubHTTPError:
            logger.warning("snapshot: push failed", exc_info=True)
            return ""
        except Exception:
            logger.warning("snapshot: push failed", exc_info=True)
            return ""
        finally:
            if metadata_path is not None and metadata_path.exists():
                metadata_path.unlink()

        commit_hash = str(getattr(commit_info, "oid", "") or "")
        self.last_snapshot_sha256 = sha256
        self.last_snapshot_size_bytes = size_bytes
        logger.info(
            "snapshot: pushed %s (size=%sKB, delta=%sKB)",
            commit_hash or "unknown",
            size_bytes // 1024,
            delta_bytes // 1024,
        )
        return commit_hash
