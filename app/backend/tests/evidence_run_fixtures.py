from __future__ import annotations

import json
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from app.backend.app.evidence.runs import (
    CompletedEvidenceRun,
    create_completed_evidence_run,
    create_evidence_run_artifact,
)

_ASOS_BUNDLE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "evidence"
    / "asos"
    / "bundles"
    / "d53f0e.tmk"
)


@lru_cache(maxsize=8)
def completed_asos_run(
    *,
    origin_job_id: str = "job_asos_d53f0e",
    origin_job_revision: int = 1,
) -> CompletedEvidenceRun:
    with zipfile.ZipFile(_ASOS_BUNDLE) as archive:
        manifest = cast(dict[str, Any], json.loads(archive.read("manifest.json")))
        artifacts = tuple(
            create_evidence_run_artifact(
                path=cast(str, entry["path"]),
                role=cast(Any, entry["role"]),
                media_type=cast(str, entry["media_type"]),
                schema_id=cast(str | None, entry.get("schema_id")),
                payload=archive.read(cast(str, entry["path"])),
            )
            for entry in cast(list[dict[str, Any]], manifest["entries"])
        )
    return create_completed_evidence_run(
        origin_job_id=origin_job_id,
        origin_job_revision=origin_job_revision,
        sealed_at=cast(str, manifest["created_at"]),
        artifacts=artifacts,
    )
