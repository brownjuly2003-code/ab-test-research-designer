from __future__ import annotations

from pathlib import Path

import pytest

from app.backend.app.evidence.artifact_store import (
    ArtifactStoreCorruptionError,
    FileArtifactStore,
)
from app.backend.tests.evidence_run_fixtures import completed_asos_run


def test_file_artifact_store_is_content_addressed_and_idempotent(
    tmp_path: Path,
) -> None:
    artifact = completed_asos_run().artifacts[0]
    store = FileArtifactStore(tmp_path / "artifacts")

    first_key = store.put(artifact.payload, expected_digest=artifact.digest)
    second_key = store.put(artifact.payload, expected_digest=artifact.digest)

    assert first_key == second_key
    assert first_key == f"sha256/{artifact.digest[7:9]}/{artifact.digest[7:]}"
    assert store.get(first_key, expected_digest=artifact.digest, expected_size=artifact.size) == artifact.payload


@pytest.mark.parametrize("mutation", ["tampered", "missing"])
def test_file_artifact_store_fails_closed_for_untrusted_disk_state(
    tmp_path: Path,
    mutation: str,
) -> None:
    artifact = completed_asos_run().artifacts[0]
    root = tmp_path / "artifacts"
    store = FileArtifactStore(root)
    storage_key = store.put(artifact.payload, expected_digest=artifact.digest)
    stored_path = root / Path(storage_key)
    if mutation == "tampered":
        stored_path.write_bytes(b"tampered")
    else:
        stored_path.unlink()

    with pytest.raises(ArtifactStoreCorruptionError, match=artifact.digest):
        store.get(
            storage_key,
            expected_digest=artifact.digest,
            expected_size=artifact.size,
        )
