"""Seed persisted ASOS evidence runs for the source-checkout demo runtime."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, cast

from app.backend.app.config import get_settings
from app.backend.app.evidence._common import load_ijson_object
from app.backend.app.evidence.lifecycle_store import LifecycleEvidenceRunStore
from app.backend.app.evidence.pipeline import run_protocol
from app.backend.app.evidence.protocol_io import FrozenProtocol, freeze
from app.backend.app.evidence.run_abx import materialize_completed_run_logical_abx
from app.backend.app.evidence.runs import CompletedEvidenceRun
from app.backend.app.repository import ProjectRepository

_ASOS_EXPERIMENT_IDS = ("d53f0e", "26bd38", "834947")
_DEFAULT_ASOS_ROOT = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "evidence" / "asos"
)


def _frozen_protocol(bundle: Path) -> FrozenProtocol:
    with zipfile.ZipFile(bundle) as archive:
        protocol = load_ijson_object(archive.read("protocol/protocol.json"))
    analysis = cast(dict[str, Any], protocol["analysis"])
    analysis["method"] = {
        "method_id": "binary_pooled_z_newcombe",
        "method_version": "binary_pooled_z_newcombe_v1",
    }
    analysis["random_seed"] = 20260901
    estimand = cast(dict[str, Any], protocol["estimand"])
    estimand["effect_measure"] = "risk_difference"
    for intervention in cast(list[dict[str, Any]], protocol["interventions"]):
        intervention["hash_version"] = "assignment_v1"
    return freeze(protocol)


def seed_asos_evidence_runs(
    repository: ProjectRepository,
    *,
    artifact_root: Path | None = None,
    source_root: Path = _DEFAULT_ASOS_ROOT,
) -> tuple[CompletedEvidenceRun, ...]:
    """Create the three deterministic public-benchmark runs once.

    ``artifact_root`` defaults to the configured one rather than to a literal, so
    the seeded runs land in the tree the API serves however this is called.
    """

    if artifact_root is None:
        artifact_root = get_settings().artifact_root
    store = LifecycleEvidenceRunStore(repository, artifact_root)
    seeded: list[CompletedEvidenceRun] = []
    for experiment_id in _ASOS_EXPERIMENT_IDS:
        run = run_protocol(
            _frozen_protocol(source_root / "bundles" / f"{experiment_id}.tmk"),
            source_root / f"{experiment_id}.parquet",
            principal="local-operator",
            out_store=store,
        )
        logical = materialize_completed_run_logical_abx(run)
        store.complete(
            run,
            bundle_id=logical.bundle_id,
            artifact_ref=f"/api/v2/runs/{run.run_id}:bundle",
        )
        seeded.append(run)
    return tuple(seeded)


__all__ = ["seed_asos_evidence_runs"]
