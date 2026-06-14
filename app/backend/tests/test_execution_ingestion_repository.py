from pathlib import Path
import sys
import uuid

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.errors import ApiError
from app.backend.app.repository import ProjectRepository


def _repo() -> ProjectRepository:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"
    return ProjectRepository(str(db_path))


def _project(repo: ProjectRepository) -> str:
    project = repo.create_project(
        {
            "project": {"project_name": "Ingest exp"},
            "hypothesis": {},
            "setup": {},
            "metrics": {},
            "constraints": {},
            "additional_context": {},
        }
    )
    return project["id"]


def test_record_exposures_first_exposure_wins_is_sticky() -> None:
    repo = _repo()
    exp = _project(repo)

    first = repo.record_exposures(
        exp,
        [{"user_id": "u1", "variation_index": 0}, {"user_id": "u2", "variation_index": 1}],
    )
    assert first == {"received": 2, "recorded": 2, "deduplicated": 0}

    # Re-exposing u1 (even to a different variation) is dropped — first exposure is sticky.
    second = repo.record_exposures(exp, [{"user_id": "u1", "variation_index": 1}])
    assert second == {"received": 1, "recorded": 0, "deduplicated": 1}

    summary = repo.get_ingestion_summary(exp)
    assert summary is not None
    assert summary["exposures_total"] == 2
    counts = {bucket["variation_index"]: bucket["count"] for bucket in summary["exposure_counts"]}
    assert counts == {0: 1, 1: 1}


def test_record_exposures_dedups_within_a_single_batch() -> None:
    repo = _repo()
    exp = _project(repo)

    result = repo.record_exposures(
        exp,
        [{"user_id": "dup", "variation_index": 0}, {"user_id": "dup", "variation_index": 1}],
    )
    assert result == {"received": 2, "recorded": 1, "deduplicated": 1}


def test_record_conversions_dedup_on_idempotency_key() -> None:
    repo = _repo()
    exp = _project(repo)

    first = repo.record_conversions(exp, [{"user_id": "u1", "metric": "purchase", "idempotency_key": "k1"}])
    assert first == {"received": 1, "recorded": 1, "deduplicated": 0}

    retry = repo.record_conversions(exp, [{"user_id": "u1", "metric": "purchase", "idempotency_key": "k1"}])
    assert retry == {"received": 1, "recorded": 0, "deduplicated": 1}


def test_record_conversions_without_key_are_always_recorded() -> None:
    repo = _repo()
    exp = _project(repo)

    repo.record_conversions(exp, [{"user_id": "u1", "metric": "purchase"}])
    repo.record_conversions(exp, [{"user_id": "u1", "metric": "purchase"}])

    summary = repo.get_ingestion_summary(exp)
    assert summary is not None
    conv = {bucket["metric"]: bucket for bucket in summary["conversion_counts"]}
    assert conv["purchase"]["count"] == 2
    assert conv["purchase"]["value_sum"] == 2.0


def test_conversion_summary_groups_by_metric_and_sums_value() -> None:
    repo = _repo()
    exp = _project(repo)

    repo.record_conversions(
        exp,
        [
            {"user_id": "u1", "metric": "revenue", "value": 12.5},
            {"user_id": "u2", "metric": "revenue", "value": 7.5},
            {"user_id": "u1", "metric": "signup", "value": 1.0},
        ],
    )

    summary = repo.get_ingestion_summary(exp)
    assert summary is not None
    conv = {bucket["metric"]: bucket for bucket in summary["conversion_counts"]}
    assert conv["revenue"]["count"] == 2
    assert conv["revenue"]["value_sum"] == 20.0
    assert conv["signup"]["count"] == 1
    assert summary["conversions_total"] == 3


def test_ingestion_summary_empty_for_fresh_experiment() -> None:
    repo = _repo()
    exp = _project(repo)

    summary = repo.get_ingestion_summary(exp)
    assert summary == {
        "experiment_id": exp,
        "exposures_total": 0,
        "exposure_counts": [],
        "conversions_total": 0,
        "conversion_counts": [],
    }


def test_ingestion_summary_none_for_unknown_experiment() -> None:
    repo = _repo()
    assert repo.get_ingestion_summary("nope") is None


def test_get_user_exposure_returns_recorded_variation_and_none_otherwise() -> None:
    repo = _repo()
    exp = _project(repo)

    assert repo.get_user_exposure(exp, "u1") is None  # nothing recorded yet

    repo.record_exposures(exp, [{"user_id": "u1", "variation_index": 1}])
    # A re-exposure to a different variation is dropped (sticky), so the stored value stays 1.
    repo.record_exposures(exp, [{"user_id": "u1", "variation_index": 0}])

    exposure = repo.get_user_exposure(exp, "u1")
    assert exposure is not None
    assert exposure["variation_index"] == 1
    assert repo.get_user_exposure(exp, "other-user") is None


def test_record_exposures_rejects_unknown_experiment() -> None:
    repo = _repo()
    with pytest.raises(ApiError):
        repo.record_exposures("nope", [{"user_id": "u1", "variation_index": 0}])


def test_record_exposures_rejects_archived_experiment() -> None:
    repo = _repo()
    exp = _project(repo)
    repo.archive_project(exp)
    with pytest.raises(ApiError):
        repo.record_exposures(exp, [{"user_id": "u1", "variation_index": 0}])


def test_deleting_experiment_cascades_ingestion_rows() -> None:
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(exp, [{"user_id": "u1", "variation_index": 0}])
    repo.record_conversions(exp, [{"user_id": "u1", "metric": "purchase"}])

    repo.delete_project(exp)

    # Re-creating the row set under a fresh project id must start clean (cascade removed rows).
    assert repo.get_ingestion_summary(exp) is None
