"""Ingestion reliability under load (P4.6).

Proves the dedup invariants hold at production scale under retried (at-least-once)
delivery: a redelivered batch must record nothing and must not inflate stored totals
or arm balance (which would manufacture a false SRM / inflate the effect).
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.repository import ProjectRepository

N = 10_000


def _repo() -> ProjectRepository:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"
    return ProjectRepository(str(db_path))


def _project(repo: ProjectRepository) -> str:
    project = repo.create_project(
        {
            "project": {"project_name": "Ingest load"},
            "hypothesis": {},
            "setup": {},
            "metrics": {},
            "constraints": {},
            "additional_context": {},
        }
    )
    return project["id"]


def _exposure_batch(n: int, *, variations: int = 2, offset: int = 0) -> list[dict[str, object]]:
    return [
        {"user_id": f"u{i}", "variation_index": i % variations}
        for i in range(offset, offset + n)
    ]


def test_exposure_ingestion_is_idempotent_under_load() -> None:
    repo = _repo()
    exp = _project(repo)
    batch = _exposure_batch(N)

    first = repo.record_exposures(exp, batch)
    assert first == {"received": N, "recorded": N, "deduplicated": 0}

    # Re-ingesting the identical batch (a client retry / at-least-once redelivery) records nothing.
    replay = repo.record_exposures(exp, batch)
    assert replay == {"received": N, "recorded": 0, "deduplicated": N}

    summary = repo.get_ingestion_summary(exp)
    assert summary is not None
    assert summary["exposures_total"] == N  # not 2N — dedup absorbs the full replay


def test_exposure_load_preserves_arm_balance_invariant() -> None:
    repo = _repo()
    exp = _project(repo)

    repo.record_exposures(exp, _exposure_batch(N, variations=2))
    # A duplicate redelivery must not inflate either arm (would manufacture a false SRM).
    repo.record_exposures(exp, _exposure_batch(N, variations=2))

    summary = repo.get_ingestion_summary(exp)
    assert summary is not None
    counts = {bucket["variation_index"]: bucket["count"] for bucket in summary["exposure_counts"]}
    assert counts == {0: N // 2, 1: N // 2}


def test_conversion_ingestion_is_idempotent_under_load() -> None:
    repo = _repo()
    exp = _project(repo)
    batch = [
        {"user_id": f"u{i}", "metric": "purchase", "idempotency_key": f"k{i}"}
        for i in range(N)
    ]

    first = repo.record_conversions(exp, batch)
    assert first == {"received": N, "recorded": N, "deduplicated": 0}

    # Keyed retries are fully deduplicated.
    replay = repo.record_conversions(exp, batch)
    assert replay == {"received": N, "recorded": 0, "deduplicated": N}


def test_mixed_batch_dedups_only_seen_users_at_scale() -> None:
    repo = _repo()
    exp = _project(repo)

    # First half already ingested (users u0..u{N/2-1}).
    repo.record_exposures(exp, _exposure_batch(N // 2))

    # A 10k batch that overlaps the first half: only the new half is recorded.
    result = repo.record_exposures(exp, _exposure_batch(N))
    assert result == {"received": N, "recorded": N // 2, "deduplicated": N // 2}
    # Accounting invariant always holds.
    assert result["received"] == result["recorded"] + result["deduplicated"]

    summary = repo.get_ingestion_summary(exp)
    assert summary is not None
    assert summary["exposures_total"] == N
