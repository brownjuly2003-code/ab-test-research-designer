from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.backend.app.evidence._common import canonical_json_bytes, sha256_hex
from app.backend.app.evidence.cli import main
from app.backend.app.evidence.gate3 import (
    Gate3Error,
    build_gate3_report,
    evaluate_gate3,
    gate3_report_digest,
    load_pilot_cohort,
    render_gate3_report,
    write_gate3_report,
)
from app.backend.app.evidence.pilot_records import (
    PilotSessionRecord,
    write_pilot_record,
)

ALPHA = "anon_00000000000000a1"
BETA = "anon_00000000000000b2"
GAMMA = "anon_00000000000000c3"


def _census(participant: str, day: int) -> dict[str, Any]:
    return {
        "bundle_id": sha256_hex(f"{participant}:{day}".encode()),
        "run_id": f"run_{participant}_{day:02d}",
        "artifact_count": 7,
        "source_artifact_count": 1,
        "estimate_count": 1,
        "row_level_artifact_count": 0,
        "aggregate_only": True,
        "evidence_type": "external_pilot",
        "partner_approved": True,
        "lineage_verdict": "pass",
        "privacy_verdict": "pass",
    }


def _record(
    participant: str,
    *,
    day: int = 4,
    outcome: str = "completed",
    seconds: int = 600,
    reuse: bool = False,
) -> PilotSessionRecord:
    """Build a genuinely valid record without running a protocol for it.

    Everything the aggregator reads lives in the record, so the tests exercise
    the aggregation rather than re-testing the bundle census that
    ``test_binary_aggregate_pipeline.py`` already covers.
    """

    source_ready_at = f"2026-09-{day:02d}T18:00:00Z"
    document: dict[str, Any] = {
        "schema_version": "1",
        "participant_ref": participant,
        "session_date": f"2026-09-{day:02d}",
        "outcome": outcome,
        "external_practitioner": True,
        "practitioner_owned_source": True,
        "source_kind": "aggregate_csv",
        "source_rows_copied": 0,
        "source_ready_at": source_ready_at,
        "bundle_ready_at": None,
        "time_to_bundle_seconds": None,
        "bundle": None,
        "reuse": {
            "observed": reuse,
            "kind": "second_run" if reuse else None,
            "observed_at": f"2026-09-{day:02d}T19:00:00Z" if reuse else None,
        },
        "measurements": {
            "completed_cycles": {"numerator": 0, "denominator": 1},
            "bundle_privacy": {"numerator": 0, "denominator": 0},
            "estimate_lineage": {"numerator": 0, "denominator": 0},
        },
    }
    if outcome == "completed":
        minutes, remainder = divmod(seconds, 60)
        hour, minute = divmod(minutes, 60)
        document["bundle_ready_at"] = (
            f"2026-09-{day:02d}T{18 + hour:02d}:{minute:02d}:{remainder:02d}Z"
        )
        document["time_to_bundle_seconds"] = seconds
        document["bundle"] = _census(participant, day)
        document["measurements"] = {
            "completed_cycles": {"numerator": 1, "denominator": 1},
            "bundle_privacy": {"numerator": 1, "denominator": 1},
            "estimate_lineage": {"numerator": 1, "denominator": 1},
        }
    document["record_digest"] = sha256_hex(canonical_json_bytes(document))
    return PilotSessionRecord(**document)


def _cohort(root: Path, records: list[PilotSessionRecord]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for record in records:
        write_pilot_record(
            record,
            root / f"{record.session_date}-{record.participant_ref}.md",
        )
    return root


def _verdicts(report: Any) -> dict[str, str]:
    return {criterion.key: criterion.verdict for criterion in report.criteria}


def test_empty_cohort_stops_with_zero_denominators(tmp_path: Path) -> None:
    report = evaluate_gate3(_cohort(tmp_path / "pilots", []))

    assert report.verdict == "stop"
    assert report.participants == 0
    assert report.records == ()
    assert report.median_time_to_bundle_seconds is None
    assert all(criterion.denominator == 0 for criterion in report.criteria)
    assert _verdicts(report) == {
        "completed_cycles": "fail",
        "repeat_use": "fail",
        "time_to_bundle": "unmeasured",
        "preflight_detection": "unmeasured",
        "estimate_lineage": "unmeasured",
        "bundle_privacy": "unmeasured",
    }


def test_incomplete_cohort_stops_because_no_cycle_completed(tmp_path: Path) -> None:
    report = evaluate_gate3(
        _cohort(
            tmp_path / "pilots",
            [
                _record(ALPHA, day=4, outcome="incomplete"),
                _record(BETA, day=5, outcome="incomplete"),
                _record(GAMMA, day=6, outcome="incomplete"),
            ],
        )
    )

    assert report.verdict == "stop"
    assert report.participants == 3
    assert report.completed_sessions == 0
    verdicts = _verdicts(report)
    assert verdicts["completed_cycles"] == "fail"
    # An incomplete session bundles nothing, so there is no rate to take. A
    # denominator of zero is not a clean sheet.
    assert verdicts["bundle_privacy"] == "unmeasured"
    assert verdicts["estimate_lineage"] == "unmeasured"


def test_three_completing_participants_with_reuse_continue(tmp_path: Path) -> None:
    report = evaluate_gate3(
        _cohort(
            tmp_path / "pilots",
            [
                _record(ALPHA, day=4, seconds=300, reuse=True),
                _record(BETA, day=5, seconds=600, reuse=True),
                _record(GAMMA, day=6, seconds=900),
            ],
        )
    )

    assert report.verdict == "continue"
    assert report.participants == 3
    assert report.median_time_to_bundle_seconds == 600
    assert _verdicts(report) == {
        "completed_cycles": "pass",
        "repeat_use": "pass",
        "time_to_bundle": "pass",
        "preflight_detection": "unmeasured",
        "estimate_lineage": "pass",
        "bundle_privacy": "pass",
    }


def test_cohort_without_reuse_pivots(tmp_path: Path) -> None:
    report = evaluate_gate3(
        _cohort(
            tmp_path / "pilots",
            [
                _record(ALPHA, day=4),
                _record(BETA, day=5),
                _record(GAMMA, day=6),
            ],
        )
    )

    assert report.verdict == "pivot"
    verdicts = _verdicts(report)
    assert verdicts["completed_cycles"] == "pass"
    assert verdicts["repeat_use"] == "fail"


def test_duplicate_participant_is_one_cycle_and_reuse_only_when_marked(
    tmp_path: Path,
) -> None:
    """Three sessions, two participants: enthusiasm is not breadth."""

    report = evaluate_gate3(
        _cohort(
            tmp_path / "pilots",
            [
                _record(ALPHA, day=4),
                _record(ALPHA, day=5, reuse=True),
                _record(BETA, day=6),
            ],
        )
    )

    assert report.participants == 2
    assert report.completed_sessions == 3
    completed = next(
        criterion
        for criterion in report.criteria
        if criterion.key == "completed_cycles"
    )
    repeat = next(
        criterion for criterion in report.criteria if criterion.key == "repeat_use"
    )
    assert (completed.numerator, completed.denominator) == (2, 2)
    assert (repeat.numerator, repeat.denominator) == (1, 2)
    assert report.verdict == "pivot"


def test_a_slow_cohort_fails_on_the_median_not_the_worst_session(
    tmp_path: Path,
) -> None:
    report = evaluate_gate3(
        _cohort(
            tmp_path / "pilots",
            [
                _record(ALPHA, day=4, seconds=1200, reuse=True),
                _record(BETA, day=5, seconds=1800, reuse=True),
                _record(GAMMA, day=6, seconds=60),
            ],
        )
    )

    assert report.median_time_to_bundle_seconds == 1200
    timing = next(
        criterion
        for criterion in report.criteria
        if criterion.key == "time_to_bundle"
    )
    assert timing.verdict == "fail"
    # One session was inside the budget; the numerator says so even though the
    # median is what decides.
    assert (timing.numerator, timing.denominator) == (1, 3)
    assert report.verdict == "pivot"


def test_incomplete_sessions_stay_out_of_the_median(tmp_path: Path) -> None:
    report = evaluate_gate3(
        _cohort(
            tmp_path / "pilots",
            [
                _record(ALPHA, day=4, seconds=300),
                _record(BETA, day=5, outcome="incomplete"),
            ],
        )
    )

    assert report.completed_sessions == 1
    assert report.median_time_to_bundle_seconds == 300
    timing = next(
        criterion
        for criterion in report.criteria
        if criterion.key == "time_to_bundle"
    )
    assert timing.denominator == 1


def test_a_non_pilot_file_is_an_error_not_a_skip(tmp_path: Path) -> None:
    root = _cohort(tmp_path / "pilots", [_record(ALPHA, day=4)])
    (root / "notes.md").write_text("free-form notes\n", encoding="utf-8")

    with pytest.raises(Gate3Error, match="notes.md is not a pilot record"):
        load_pilot_cohort(root)


def test_a_missing_directory_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(Gate3Error, match="does not exist"):
        load_pilot_cohort(tmp_path / "absent")


def test_rendered_report_is_byte_identical_on_a_second_run(tmp_path: Path) -> None:
    root = _cohort(
        tmp_path / "pilots",
        [_record(ALPHA, day=4, reuse=True), _record(BETA, day=5)],
    )
    destination = tmp_path / "gate3_2026-09-08.md"

    write_gate3_report(evaluate_gate3(root), destination)
    first = destination.read_bytes()
    write_gate3_report(evaluate_gate3(root), destination)

    assert destination.read_bytes() == first


def test_report_digest_covers_every_field_but_itself(tmp_path: Path) -> None:
    report = evaluate_gate3(_cohort(tmp_path / "pilots", [_record(ALPHA, day=4)]))
    rendered = render_gate3_report(report).decode()
    _, _, remainder = rendered.partition("```json\n")
    payload, _, _ = remainder.partition("\n```\n")
    document = json.loads(payload)

    recomputed = sha256_hex(
        canonical_json_bytes(
            {
                key: value
                for key, value in document.items()
                if key != "report_digest"
            }
        )
    )

    assert recomputed == report.report_digest == gate3_report_digest(report)


def test_a_changed_cohort_changes_the_digest(tmp_path: Path) -> None:
    one = build_gate3_report([_record(ALPHA, day=4)])
    two = build_gate3_report([_record(ALPHA, day=4), _record(BETA, day=5)])

    assert one.report_digest != two.report_digest


def test_cli_writes_the_report_and_exits_zero_on_stop(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _cohort(tmp_path / "pilots", [_record(ALPHA, day=4, outcome="incomplete")])
    destination = tmp_path / "gates" / "gate3_2026-09-08.md"

    exit_code = main(
        ["gate3", "--records", str(root), "--out", str(destination)]
    )

    # `stop` is a measurement, not a crash: a CI step must not read the exit
    # status as "the aggregator failed".
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is True
    assert payload["verdict"] == "stop"
    assert payload["participants"] == 1
    assert destination.read_text(encoding="utf-8").startswith("# Gate 3 decision")


def test_cli_reports_a_non_pilot_file_as_a_gate3_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _cohort(tmp_path / "pilots", [_record(ALPHA, day=4)])
    (root / "README.md").write_text("# pilots\n", encoding="utf-8")

    exit_code = main(["gate3", "--records", str(root)])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is False
    assert payload["error"]["code"] == "gate3_error"
