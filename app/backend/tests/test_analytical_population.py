"""Canonical analytical population contract (audit F-02 / plan step 3).

Reproduces the two holdout/primary mismatch cases from audit_gpt_23_07_26 and
locks shared identity + exclusion semantics across primary, holdout, timing, and strata.
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.constants import BOT_CONVERSION_EVENT_THRESHOLD
from app.backend.app.repository import ProjectRepository
from app.backend.app.repository.execution.population import (
    ANALYTICAL_POPULATION_POLICY_VERSION,
)
from app.backend.app.services.live_stats_service import build_live_stats


def _repo() -> ProjectRepository:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    return ProjectRepository(str(temp_dir / f"{uuid.uuid4()}.sqlite3"))


def _project(repo: ProjectRepository) -> str:
    project = repo.create_project(
        {
            "project": {"project_name": "Population contract"},
            "hypothesis": {},
            "setup": {},
            "metrics": {},
            "constraints": {},
            "additional_context": {},
        }
    )
    return project["id"]


def _at(hours: float) -> str:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return (base + timedelta(hours=hours)).isoformat()


def test_holdout_exclusion_case_matches_audit_f02() -> None:
    """Audit F-02 EXCLUSION_CASE: manual exclude one of two holdout converters → 1/1."""
    repo = _repo()
    exp = _project(repo)
    repo.record_holdout(exp, [{"user_id": "h1"}, {"user_id": "h2"}])
    repo.record_conversions(
        exp,
        [
            {"user_id": "h1", "metric": "purchase", "value": 1.0},
            {"user_id": "h2", "metric": "purchase", "value": 1.0},
        ],
    )
    repo.record_exclusions(exp, [{"user_id": "h1", "exclusion_reason": "qa"}])

    holdout = repo.get_holdout_aggregates(exp, "purchase")
    assert holdout is not None
    assert holdout["holdout"]["exposed_users"] == 1
    assert holdout["holdout"]["converted_users"] == 1
    assert holdout["population_policy_version"] == ANALYTICAL_POPULATION_POLICY_VERSION


def test_holdout_identity_case_matches_audit_f02() -> None:
    """Audit F-02 IDENTITY_CASE: anon holdout exposure + canonical conversion → attributed."""
    repo = _repo()
    exp = _project(repo)
    # Two holdout people: one fully under raw id, one anonymous→canonical.
    repo.record_holdout(exp, [{"user_id": "anon-a"}, {"user_id": "h2"}])
    repo.record_identities(exp, [{"anonymous_id": "anon-a", "canonical_id": "user-a"}])
    repo.record_conversions(
        exp,
        [
            {"user_id": "user-a", "metric": "purchase", "value": 1.0},
            {"user_id": "h2", "metric": "purchase", "value": 1.0},
        ],
    )

    holdout = repo.get_holdout_aggregates(exp, "purchase")
    assert holdout is not None
    assert holdout["holdout"]["exposed_users"] == 2
    assert holdout["holdout"]["converted_users"] == 2


def test_primary_and_holdout_share_identity_and_exclusion() -> None:
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [
            {"user_id": "anon-t", "variation_index": 0},
            {"user_id": "t2", "variation_index": 1},
        ],
    )
    repo.record_holdout(exp, [{"user_id": "anon-h"}, {"user_id": "h2"}])
    repo.record_identities(
        exp,
        [
            {"anonymous_id": "anon-t", "canonical_id": "user-t"},
            {"anonymous_id": "anon-h", "canonical_id": "user-h"},
        ],
    )
    repo.record_conversions(
        exp,
        [
            {"user_id": "user-t", "metric": "purchase", "value": 1.0},
            {"user_id": "t2", "metric": "purchase", "value": 1.0},
            {"user_id": "user-h", "metric": "purchase", "value": 1.0},
            {"user_id": "h2", "metric": "purchase", "value": 1.0},
        ],
    )
    repo.record_exclusions(exp, [{"user_id": "t2"}, {"user_id": "h2"}])

    primary = repo.get_experiment_analysis_aggregates(exp, "purchase")
    holdout = repo.get_holdout_aggregates(exp, "purchase")
    assert primary is not None and holdout is not None
    by_arm = {row["variation_index"]: row for row in primary["variations"]}
    assert by_arm[0]["exposed_users"] == 1
    assert by_arm[0]["converted_users"] == 1
    assert 1 not in by_arm  # t2 excluded entirely
    assert holdout["holdout"]["exposed_users"] == 1
    assert holdout["holdout"]["converted_users"] == 1
    assert primary["population_policy_version"] == holdout["population_policy_version"]


def test_event_timing_attributes_canonical_conversion_to_anonymous_exposure() -> None:
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [{"user_id": "anon", "variation_index": 0, "occurred_at": _at(0)}],
    )
    repo.record_identities(exp, [{"anonymous_id": "anon", "canonical_id": "user"}])
    repo.record_conversions(
        exp,
        [{"user_id": "user", "metric": "purchase", "occurred_at": _at(2)}],
    )

    summary = repo.get_event_timing_summary(exp, "purchase", 14.0)
    assert summary is not None
    assert summary["total"] == 1
    assert summary["in_window"] == 1
    assert summary["out_of_order"] == 0
    assert summary["population_policy_version"] == ANALYTICAL_POPULATION_POLICY_VERSION


def test_event_timing_excludes_rate_spike_and_holdout() -> None:
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [
            {"user_id": "good", "variation_index": 0, "occurred_at": _at(0)},
            {"user_id": "bot", "variation_index": 1, "occurred_at": _at(0)},
        ],
    )
    repo.record_holdout(exp, [{"user_id": "h1"}])
    repo.record_conversions(
        exp,
        [
            {"user_id": "good", "metric": "purchase", "occurred_at": _at(1)},
            {"user_id": "h1", "metric": "purchase", "occurred_at": _at(1)},
            *[
                {"user_id": "bot", "metric": "purchase", "occurred_at": _at(1 + i * 0.01)}
                for i in range(BOT_CONVERSION_EVENT_THRESHOLD + 1)
            ],
        ],
    )
    summary = repo.get_event_timing_summary(exp, "purchase", 14.0)
    assert summary is not None
    assert summary["total"] == 1
    assert summary["in_window"] == 1


def test_first_exposure_wins_after_login_reexposure() -> None:
    repo = _repo()
    exp = _project(repo)
    # Anonymous first on control, later login re-exposure on treatment collapses to control.
    repo.record_exposures(
        exp,
        [
            {"user_id": "anon", "variation_index": 0, "occurred_at": _at(0)},
            {"user_id": "user", "variation_index": 1, "occurred_at": _at(5)},
        ],
    )
    repo.record_identities(exp, [{"anonymous_id": "anon", "canonical_id": "user"}])
    repo.record_conversions(exp, [{"user_id": "user", "metric": "purchase", "value": 1.0}])

    primary = repo.get_experiment_analysis_aggregates(exp, "purchase")
    assert primary is not None
    by_arm = {row["variation_index"]: row for row in primary["variations"]}
    assert by_arm[0]["exposed_users"] == 1
    assert by_arm[0]["converted_users"] == 1
    assert 1 not in by_arm


def test_identity_alias_does_not_change_total_people() -> None:
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [
            {"user_id": "a1", "variation_index": 0},
            {"user_id": "a2", "variation_index": 0},
            {"user_id": "b1", "variation_index": 1},
        ],
    )
    before = repo.get_experiment_analysis_aggregates(exp, "purchase")
    assert before is not None
    before_n = sum(row["exposed_users"] for row in before["variations"])

    # Link a1→canon and expose under canon with same arm — still one person.
    repo.record_identities(exp, [{"anonymous_id": "a1", "canonical_id": "canon"}])
    repo.record_exposures(exp, [{"user_id": "canon", "variation_index": 0}])
    after = repo.get_experiment_analysis_aggregates(exp, "purchase")
    assert after is not None
    after_n = sum(row["exposed_users"] for row in after["variations"])
    assert after_n == before_n


def test_exclusion_removes_person_from_primary_holdout_timing_and_strata() -> None:
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [
            {"user_id": "u1", "variation_index": 0, "occurred_at": _at(0)},
            {"user_id": "u2", "variation_index": 1, "occurred_at": _at(0)},
        ],
    )
    repo.record_holdout(exp, [{"user_id": "h1"}, {"user_id": "h2"}])
    repo.record_conversions(
        exp,
        [
            {"user_id": "u1", "metric": "purchase", "occurred_at": _at(1), "value": 1.0},
            {"user_id": "u2", "metric": "purchase", "occurred_at": _at(1), "value": 1.0},
            {"user_id": "h1", "metric": "purchase", "occurred_at": _at(1), "value": 1.0},
            {"user_id": "h2", "metric": "purchase", "occurred_at": _at(1), "value": 1.0},
        ],
    )
    repo.record_strata(
        exp,
        [
            {"user_id": "u1", "stratum": "mobile"},
            {"user_id": "u2", "stratum": "mobile"},
        ],
    )
    repo.record_exclusions(exp, [{"user_id": "u1"}, {"user_id": "h1"}])

    primary = repo.get_experiment_analysis_aggregates(exp, "purchase")
    holdout = repo.get_holdout_aggregates(exp, "purchase")
    timing = repo.get_event_timing_summary(exp, "purchase", 14.0)
    strata = repo.get_stratified_aggregates(exp, "purchase")
    assert primary is not None and holdout is not None and timing is not None and strata is not None

    primary_n = sum(row["exposed_users"] for row in primary["variations"])
    assert primary_n == 1
    assert holdout["holdout"]["exposed_users"] == 1
    assert timing["total"] == 1  # only u2 remains in treated timing
    mobile = next(s for s in strata["strata"] if s["stratum"] == "mobile")
    assert sum(v["exposed_users"] for v in mobile["variations"]) == 1


def test_rate_spike_holdout_user_excluded() -> None:
    repo = _repo()
    exp = _project(repo)
    repo.record_holdout(exp, [{"user_id": "bot"}, {"user_id": "human"}])
    repo.record_conversions(
        exp,
        [
            {"user_id": "human", "metric": "purchase", "value": 1.0},
            *[
                {"user_id": "bot", "metric": "purchase", "value": 1.0}
                for _ in range(BOT_CONVERSION_EVENT_THRESHOLD + 1)
            ],
        ],
    )
    holdout = repo.get_holdout_aggregates(exp, "purchase")
    assert holdout is not None
    assert holdout["holdout"]["exposed_users"] == 1
    assert holdout["holdout"]["converted_users"] == 1


def test_identity_chain_rejected_at_ingest() -> None:
    repo = _repo()
    exp = _project(repo)
    first = repo.record_identities(exp, [{"anonymous_id": "a", "canonical_id": "b"}])
    assert first["recorded"] == 1
    # b→c would form a chain (b is already a canonical target of a). Policy: reject.
    chain = repo.record_identities(exp, [{"anonymous_id": "b", "canonical_id": "c"}])
    assert chain == {"received": 1, "recorded": 0, "deduplicated": 0}
    # z→a where a is already an anonymous_id would also extend a chain.
    reverse = repo.record_identities(exp, [{"anonymous_id": "z", "canonical_id": "a"}])
    assert reverse == {"received": 1, "recorded": 0, "deduplicated": 0}
    summary = repo.get_identity_resolution_summary(exp)
    assert summary is not None
    assert summary["linked_identities"] == 1


def test_population_diagnostics_fingerprint_and_live_stats_block() -> None:
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [
            {"user_id": "t1", "variation_index": 0},
            {"user_id": "t2", "variation_index": 1},
        ],
    )
    repo.record_holdout(exp, [{"user_id": "h1"}])
    repo.record_identities(exp, [{"anonymous_id": "t1", "canonical_id": "canon-t1"}])
    repo.record_exclusions(exp, [{"user_id": "t2"}])

    diag = repo.get_analytical_population_diagnostics(exp, "purchase")
    assert diag is not None
    assert diag["policy_version"] == ANALYTICAL_POPULATION_POLICY_VERSION
    assert diag["treated_users"] == 1  # t2 excluded
    assert diag["holdout_users"] == 1
    assert diag["manual_excluded"] == 1
    assert diag["linked_identities"] == 1
    assert diag["policy_aligned"] is True
    assert "analytical_population_v1" in diag["fingerprint"]

    primary = repo.get_experiment_analysis_aggregates(exp, "purchase")
    assert primary is not None
    live = build_live_stats(
        exp,
        {
            "metrics": {
                "primary_metric_name": "purchase",
                "metric_type": "binary",
                "baseline_value": 0.1,
                "mde_pct": 5,
                "alpha": 0.05,
                "power": 0.8,
            },
            "setup": {
                "traffic_split": [50, 50],
                "variants_count": 2,
                "expected_daily_traffic": 12000,
                "audience_share_in_test": 0.6,
            },
            "constraints": {"n_looks": 1, "analysis_mode": "frequentist"},
        },
        primary,
        population_diagnostics=diag,
    )
    assert live["population"]["status"] == "ok"
    assert live["population"]["fingerprint"] == diag["fingerprint"]
    assert live["population"]["treated_users"] == 1


def test_combined_identity_exclusion_strata_holdout_invariant() -> None:
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [
            {"user_id": "anon-a", "variation_index": 0},
            {"user_id": "b", "variation_index": 1},
            {"user_id": "c", "variation_index": 0},
        ],
    )
    repo.record_holdout(exp, [{"user_id": "anon-h"}, {"user_id": "hx"}])
    repo.record_identities(
        exp,
        [
            {"anonymous_id": "anon-a", "canonical_id": "a"},
            {"anonymous_id": "anon-h", "canonical_id": "h"},
        ],
    )
    repo.record_strata(
        exp,
        [
            {"user_id": "a", "stratum": "desktop"},
            {"user_id": "b", "stratum": "desktop"},
            {"user_id": "c", "stratum": "mobile"},
        ],
    )
    repo.record_conversions(
        exp,
        [
            {"user_id": "a", "metric": "purchase", "value": 1.0},
            {"user_id": "b", "metric": "purchase", "value": 1.0},
            {"user_id": "c", "metric": "purchase", "value": 1.0},
            {"user_id": "h", "metric": "purchase", "value": 1.0},
            {"user_id": "hx", "metric": "purchase", "value": 1.0},
        ],
    )
    repo.record_exclusions(exp, [{"user_id": "b"}, {"user_id": "hx"}])

    primary = repo.get_experiment_analysis_aggregates(exp, "purchase")
    holdout = repo.get_holdout_aggregates(exp, "purchase")
    strata = repo.get_stratified_aggregates(exp, "purchase")
    diag = repo.get_analytical_population_diagnostics(exp, "purchase")
    assert primary and holdout and strata and diag

    primary_n = sum(v["exposed_users"] for v in primary["variations"])
    assert primary_n == 2  # a, c (b excluded)
    assert holdout["holdout"]["exposed_users"] == 1  # h (hx excluded)
    assert diag["treated_users"] == primary_n
    assert diag["holdout_users"] == holdout["holdout"]["exposed_users"]

    strata_n = sum(
        v["exposed_users"] for block in strata["strata"] for v in block["variations"]
    )
    assert strata_n == 2  # a desktop + c mobile; b excluded
