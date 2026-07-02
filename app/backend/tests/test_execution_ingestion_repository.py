from datetime import UTC, datetime
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


def test_ingestion_records_event_time_occurred_at() -> None:
    """occurred_at (client event time) is stored distinctly from created_at (server-receive), and
    defaults to created_at when the event omits it (P4.1 event-time foundation)."""
    repo = _repo()
    exp = _project(repo)

    exposure_time = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    conversion_time = datetime(2026, 5, 1, 13, 0, 0, tzinfo=UTC)
    repo.record_exposures(
        exp,
        [
            {"user_id": "u1", "variation_index": 0, "occurred_at": exposure_time},
            {"user_id": "u2", "variation_index": 1},  # no occurred_at -> defaults to created_at
        ],
    )
    repo.record_conversions(
        exp,
        [
            {"user_id": "u1", "metric": "purchase", "occurred_at": conversion_time},
            {"user_id": "u2", "metric": "purchase"},  # no occurred_at -> defaults to created_at
        ],
    )

    with repo._backend._connect() as connection:  # type: ignore[attr-defined]
        exposures = {
            row["user_id"]: (row["created_at"], row["occurred_at"])
            for row in connection.execute(
                "SELECT user_id, created_at, occurred_at FROM exposures WHERE experiment_id = ?",
                (exp,),
            ).fetchall()
        }
        conversions = {
            row["user_id"]: (row["created_at"], row["occurred_at"])
            for row in connection.execute(
                "SELECT user_id, created_at, occurred_at FROM conversions WHERE experiment_id = ?",
                (exp,),
            ).fetchall()
        }

    # Supplied event time is stored (UTC-normalized), separate from the server-receive time.
    assert exposures["u1"][1] == exposure_time.isoformat()
    assert exposures["u1"][1] != exposures["u1"][0]
    assert conversions["u1"][1] == conversion_time.isoformat()
    assert conversions["u1"][1] != conversions["u1"][0]
    # Omitted event time defaults to the server-receive time (occurred_at == created_at).
    assert exposures["u2"][1] == exposures["u2"][0]
    assert conversions["u2"][1] == conversions["u2"][0]


def test_ingestion_normalizes_naive_occurred_at_to_utc() -> None:
    """A naive client timestamp (no tzinfo) is recorded as UTC, so event times are comparable (P4.1)."""
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [{"user_id": "u1", "variation_index": 0, "occurred_at": datetime(2026, 5, 1, 9, 30, 0)}],
    )

    with repo._backend._connect() as connection:  # type: ignore[attr-defined]
        occurred_at = connection.execute(
            "SELECT occurred_at FROM exposures WHERE experiment_id = ? AND user_id = ?",
            (exp, "u1"),
        ).fetchone()["occurred_at"]

    assert occurred_at == datetime(2026, 5, 1, 9, 30, 0, tzinfo=UTC).isoformat()


def test_holdout_exposure_records_occurred_at_as_received() -> None:
    """Holdout members carry no client event time, so occurred_at == created_at — keeping the
    NOT NULL event-time column populated for the -1 tail too (P4.1)."""
    repo = _repo()
    exp = _project(repo)
    repo.record_holdout(exp, [{"user_id": "h1"}])

    with repo._backend._connect() as connection:  # type: ignore[attr-defined]
        row = connection.execute(
            "SELECT created_at, occurred_at FROM exposures WHERE experiment_id = ? AND user_id = ?",
            (exp, "h1"),
        ).fetchone()

    assert row["occurred_at"] == row["created_at"]


def test_event_timing_summary_classifies_in_window_late_and_out_of_order() -> None:
    """Each conversion is classified by its event time relative to the user's exposure (P4.2):
    in-window, late (beyond the horizon), or out-of-order (before the exposure). The holdout tail
    is excluded, and the read returns None for a missing experiment."""
    repo = _repo()
    exp = _project(repo)

    def at(day: int) -> datetime:
        return datetime(2026, 5, day, 12, 0, 0, tzinfo=UTC)

    repo.record_exposures(
        exp,
        [
            {"user_id": "u1", "variation_index": 0, "occurred_at": at(1)},
            {"user_id": "u2", "variation_index": 1, "occurred_at": at(1)},
            {"user_id": "u3", "variation_index": 0, "occurred_at": at(10)},
        ],
    )
    repo.record_conversions(
        exp,
        [
            {"user_id": "u1", "metric": "purchase", "occurred_at": at(2)},  # in-window (+1d)
            {"user_id": "u2", "metric": "purchase", "occurred_at": at(20)},  # late (+19d > 14)
            {"user_id": "u3", "metric": "purchase", "occurred_at": at(8)},  # out-of-order (before)
        ],
    )
    # A holdout member's conversion must never enter the timing counts (variation_index = -1).
    repo.record_holdout(exp, [{"user_id": "h1"}])
    repo.record_conversions(exp, [{"user_id": "h1", "metric": "purchase", "occurred_at": at(2)}])

    summary = repo.get_event_timing_summary(exp, "purchase", 14.0)
    assert summary is not None
    assert summary["in_window"] == 1
    assert summary["late"] == 1
    assert summary["out_of_order"] == 1
    assert summary["total"] == 3  # holdout conversion excluded
    assert summary["horizon_days"] == 14.0

    assert repo.get_event_timing_summary("missing", "purchase", 14.0) is None


def test_event_timing_summary_defaults_omitted_event_time_to_in_window() -> None:
    """A conversion ingested without occurred_at defaults to the receive time (== exposure receive
    time here), so it lands in-window — never spuriously flagged as late/out-of-order (P4.2)."""
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(exp, [{"user_id": "u1", "variation_index": 0}])
    repo.record_conversions(exp, [{"user_id": "u1", "metric": "purchase"}])

    summary = repo.get_event_timing_summary(exp, "purchase", 14.0)
    assert summary is not None
    assert (summary["in_window"], summary["late"], summary["out_of_order"]) == (1, 0, 0)


def test_identity_resolution_empty_map_is_a_noop() -> None:
    """With no identity links the resolved rollup is byte-identical to the unresolved one (P4.3):
    the resolution is invisible to every existing path. This is the safety contract."""
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [
            {"user_id": "u1", "variation_index": 0},
            {"user_id": "u2", "variation_index": 1},
            {"user_id": "u3", "variation_index": 1},
        ],
    )
    repo.record_conversions(
        exp,
        [
            {"user_id": "u1", "metric": "purchase", "value": 2.0},
            {"user_id": "u2", "metric": "purchase"},
            {"user_id": "u2", "metric": "purchase"},  # second event for the same user
        ],
    )
    aggregates = repo.get_experiment_analysis_aggregates(exp, "purchase")
    assert aggregates is not None
    by_index = {v["variation_index"]: v for v in aggregates["variations"]}
    # Control: 1 exposed, 1 converted, value 2.0. Treatment: 2 exposed, 1 converted, u2's two
    # events fold to one converted user with value 2.0.
    assert by_index[0] == {
        "variation_index": 0,
        "exposed_users": 1,
        "converted_users": 1,
        "value_sum": 2.0,
        "value_sq_sum": 4.0,
    }
    assert by_index[1]["exposed_users"] == 2
    assert by_index[1]["converted_users"] == 1
    # No links recorded → the indicator summary reports an inactive, all-zero state.
    summary = repo.get_identity_resolution_summary(exp)
    assert summary == {
        "experiment_id": exp,
        "linked_identities": 0,
        "canonicalized_events": 0,
        "merged_users": 0,
    }


def test_identity_resolution_attributes_conversion_to_canonical() -> None:
    """A user exposed while anonymous who converts under their canonical (logged-in) id has the
    conversion attributed to the exposed arm once the anonymous → canonical link is recorded (P4.3)."""
    repo = _repo()
    exp = _project(repo)
    # 'anon' is exposed to the treatment arm; the conversion arrives under the logged-in id 'user'.
    repo.record_exposures(exp, [{"user_id": "anon", "variation_index": 1}])
    repo.record_conversions(exp, [{"user_id": "user", "metric": "purchase"}])

    before = repo.get_experiment_analysis_aggregates(exp, "purchase")
    assert before is not None
    # Without a link the conversion is orphaned — the exposed arm shows zero conversions.
    assert {v["variation_index"]: v["converted_users"] for v in before["variations"]} == {1: 0}

    repo.record_identities(exp, [{"anonymous_id": "anon", "canonical_id": "user"}])

    after = repo.get_experiment_analysis_aggregates(exp, "purchase")
    assert after is not None
    arm = next(v for v in after["variations"] if v["variation_index"] == 1)
    assert arm["exposed_users"] == 1
    assert arm["converted_users"] == 1  # now attributed to the canonical user's arm


def test_identity_resolution_collapses_reexposure_without_inflating_srm() -> None:
    """A person exposed while anonymous and re-exposed after login (two raw ids, two exposure rows)
    collapses to one canonical user — counted once, in the arm of their FIRST exposure (P4.3). This
    is the SRM-inflation fix: the duplicate exposure no longer manufactures an extra unit."""
    repo = _repo()
    exp = _project(repo)

    def at(day: int) -> datetime:
        return datetime(2026, 5, day, 12, 0, 0, tzinfo=UTC)

    # First exposure (anonymous, arm 0) precedes the post-login re-exposure (arm 1).
    repo.record_exposures(exp, [{"user_id": "anon", "variation_index": 0, "occurred_at": at(1)}])
    repo.record_exposures(exp, [{"user_id": "user", "variation_index": 1, "occurred_at": at(2)}])
    repo.record_identities(exp, [{"anonymous_id": "anon", "canonical_id": "user"}])

    aggregates = repo.get_experiment_analysis_aggregates(exp, "purchase")
    assert aggregates is not None
    total_exposed = sum(v["exposed_users"] for v in aggregates["variations"])
    assert total_exposed == 1  # one person, not two — no SRM inflation
    by_index = {v["variation_index"]: v["exposed_users"] for v in aggregates["variations"]}
    assert by_index == {0: 1}  # first-exposure-wins keeps the earlier (arm 0) assignment


def test_identity_resolution_first_write_wins_canonical() -> None:
    """An anonymous id maps to exactly one canonical id: a later re-link for the same anonymous id is
    dropped (first-write-wins), and a self-link is skipped (P4.3)."""
    repo = _repo()
    exp = _project(repo)
    first = repo.record_identities(exp, [{"anonymous_id": "a", "canonical_id": "c1"}])
    assert first["recorded"] == 1
    # Re-link the same anonymous id to a different canonical → dropped.
    second = repo.record_identities(exp, [{"anonymous_id": "a", "canonical_id": "c2"}])
    assert second["recorded"] == 0
    assert second["deduplicated"] == 1
    # A self-link is a no-op and is neither recorded nor counted as a dedup.
    selflink = repo.record_identities(exp, [{"anonymous_id": "b", "canonical_id": "b"}])
    assert selflink == {"received": 1, "recorded": 0, "deduplicated": 0}

    # Resolution still points 'a' at the first canonical 'c1'.
    repo.record_exposures(exp, [{"user_id": "a", "variation_index": 1}])
    repo.record_conversions(exp, [{"user_id": "c1", "metric": "purchase"}])
    aggregates = repo.get_experiment_analysis_aggregates(exp, "purchase")
    assert aggregates is not None
    arm = next(v for v in aggregates["variations"] if v["variation_index"] == 1)
    assert arm["converted_users"] == 1


def test_identity_resolution_summary_counts_and_missing_experiment() -> None:
    """The indicator summary counts active links, re-attributed events, and merged users; the events
    counted are only those recorded under a linked anonymous id (P4.3)."""
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [
            {"user_id": "anon1", "variation_index": 0},  # linked, under anonymous id
            {"user_id": "user2", "variation_index": 1},  # unlinked
        ],
    )
    repo.record_conversions(exp, [{"user_id": "anon1", "metric": "purchase"}])  # linked, anonymous
    repo.record_identities(
        exp,
        [
            {"anonymous_id": "anon1", "canonical_id": "user1"},  # has events → a real merge
            {"anonymous_id": "ghost", "canonical_id": "user9"},  # linked but no events
        ],
    )
    summary = repo.get_identity_resolution_summary(exp)
    assert summary is not None
    assert summary["linked_identities"] == 2
    # anon1's exposure + anon1's conversion are under an anonymous id → 2 canonicalized events.
    assert summary["canonicalized_events"] == 2
    # Only 'user1' absorbed real events; 'ghost' has none.
    assert summary["merged_users"] == 1

    assert repo.get_identity_resolution_summary("missing") is None


def test_exclusion_empty_is_a_noop() -> None:
    """With no manual exclusions and no rate-spike user, the rollup is unchanged and the exclusion
    summary reports an inactive, all-zero state (P4.4) — the filter is invisible by default."""
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [{"user_id": "u1", "variation_index": 0}, {"user_id": "u2", "variation_index": 1}],
    )
    repo.record_conversions(exp, [{"user_id": "u1", "metric": "purchase"}])
    aggregates = repo.get_experiment_analysis_aggregates(exp, "purchase")
    assert aggregates is not None
    assert {v["variation_index"]: v["exposed_users"] for v in aggregates["variations"]} == {0: 1, 1: 1}
    assert repo.get_exclusion_summary(exp, "purchase") == {
        "experiment_id": exp,
        "total_filtered": 0,
        "manual_filtered": 0,
        "rate_spike_filtered": 0,
    }
    assert repo.get_exclusion_summary("missing", "purchase") is None


def test_exclusion_manual_deny_list_removes_user_from_aggregates() -> None:
    """A user on the manual deny-list is dropped from every per-variation count, and the underlying
    events are not deleted (P4.4). First-write-wins keeps the first reason."""
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [
            {"user_id": "good", "variation_index": 1},
            {"user_id": "bad", "variation_index": 1},
        ],
    )
    repo.record_conversions(exp, [{"user_id": "good", "metric": "purchase"}])
    repo.record_conversions(exp, [{"user_id": "bad", "metric": "purchase"}])

    result = repo.record_exclusions(exp, [{"user_id": "bad", "exclusion_reason": "fraud_ring"}])
    assert result["recorded"] == 1
    # A second exclusion for the same user is dropped (first reason sticks).
    assert repo.record_exclusions(exp, [{"user_id": "bad", "exclusion_reason": "other"}])["recorded"] == 0

    aggregates = repo.get_experiment_analysis_aggregates(exp, "purchase")
    assert aggregates is not None
    arm = next(v for v in aggregates["variations"] if v["variation_index"] == 1)
    assert arm["exposed_users"] == 1  # 'bad' removed
    assert arm["converted_users"] == 1  # only 'good'
    summary = repo.get_exclusion_summary(exp, "purchase")
    assert summary == {
        "experiment_id": exp,
        "total_filtered": 1,
        "manual_filtered": 1,
        "rate_spike_filtered": 0,
    }
    # The raw events are still present — exclusion is a read-time filter, not a delete.
    assert repo.get_ingestion_summary(exp)["exposures_total"] == 2


def test_exclusion_rate_spike_auto_filters_a_bot() -> None:
    """A user with more than BOT_CONVERSION_EVENT_THRESHOLD conversion events on the metric is treated
    as an automation artifact and removed from the rollup (P4.4) — without any manual deny-list entry."""
    from app.backend.app.constants import BOT_CONVERSION_EVENT_THRESHOLD

    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [{"user_id": "human", "variation_index": 1}, {"user_id": "bot", "variation_index": 1}],
    )
    repo.record_conversions(exp, [{"user_id": "human", "metric": "purchase"}])
    # The bot spams just over the threshold (distinct idempotency keys so all are recorded).
    repo.record_conversions(
        exp,
        [
            {"user_id": "bot", "metric": "purchase", "idempotency_key": f"k{i}"}
            for i in range(BOT_CONVERSION_EVENT_THRESHOLD + 1)
        ],
    )

    aggregates = repo.get_experiment_analysis_aggregates(exp, "purchase")
    assert aggregates is not None
    arm = next(v for v in aggregates["variations"] if v["variation_index"] == 1)
    assert arm["exposed_users"] == 1  # bot removed, only 'human' counts
    summary = repo.get_exclusion_summary(exp, "purchase")
    assert summary["rate_spike_filtered"] == 1
    assert summary["manual_filtered"] == 0
    assert summary["total_filtered"] == 1


def test_exclusion_rate_spike_is_global_across_metrics() -> None:
    """A user who only spams the primary metric must still be excluded from a guardrail metric's own
    rollup (P1.2 fix, audit finding D) — otherwise the primary and guardrail blocks report a different
    ``exposed_users`` for the same arm, because a metric-scoped rate-spike check only ever sees the
    bot's events on the metric it happens to spam. Bot detection is a property of the user, so it is
    computed once across every metric in the experiment and reused by every metric's rollup."""
    from app.backend.app.constants import BOT_CONVERSION_EVENT_THRESHOLD

    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [{"user_id": "human", "variation_index": 1}, {"user_id": "bot", "variation_index": 1}],
    )
    # The bot spams only the primary metric — never touches the guardrail metric at all.
    repo.record_conversions(exp, [{"user_id": "human", "metric": "purchase"}])
    repo.record_conversions(exp, [{"user_id": "human", "metric": "error_rate"}])
    repo.record_conversions(
        exp,
        [
            {"user_id": "bot", "metric": "purchase", "idempotency_key": f"k{i}"}
            for i in range(BOT_CONVERSION_EVENT_THRESHOLD + 1)
        ],
    )

    primary = repo.get_experiment_analysis_aggregates(exp, "purchase")
    guardrail = repo.get_experiment_analysis_aggregates(exp, "error_rate")
    assert primary is not None and guardrail is not None
    primary_arm = next(v for v in primary["variations"] if v["variation_index"] == 1)
    guardrail_arm = next(v for v in guardrail["variations"] if v["variation_index"] == 1)
    assert primary_arm["exposed_users"] == 1  # bot removed from the metric it spammed
    # Bot removed from the guardrail too, even though it has zero events on that metric.
    assert guardrail_arm["exposed_users"] == 1
    assert guardrail_arm["exposed_users"] == primary_arm["exposed_users"]


def test_exclusion_manual_and_rate_spike_are_disjoint() -> None:
    """A user that is both manually excluded and a rate-spike counts once, under manual (P4.4) — the
    per-reason split stays disjoint so manual + rate_spike == total."""
    from app.backend.app.constants import BOT_CONVERSION_EVENT_THRESHOLD

    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(exp, [{"user_id": "both", "variation_index": 1}, {"user_id": "ok", "variation_index": 1}])
    repo.record_conversions(
        exp,
        [
            {"user_id": "both", "metric": "purchase", "idempotency_key": f"k{i}"}
            for i in range(BOT_CONVERSION_EVENT_THRESHOLD + 1)
        ],
    )
    repo.record_exclusions(exp, [{"user_id": "both", "exclusion_reason": "manual_too"}])

    summary = repo.get_exclusion_summary(exp, "purchase")
    assert summary["manual_filtered"] == 1
    assert summary["rate_spike_filtered"] == 0  # 'both' is attributed to manual, not double-counted
    assert summary["total_filtered"] == 1
