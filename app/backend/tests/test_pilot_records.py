from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.backend.app.evidence._common import canonical_json_bytes, sha256_hex
from app.backend.app.evidence.cli import main
from app.backend.app.evidence.pilot_records import (
    PilotRecordValidationError,
    create_pilot_session_record,
    load_pilot_record,
    write_pilot_record,
)

ASOS_BUNDLE = (
    Path(__file__).parent
    / "fixtures"
    / "evidence"
    / "asos"
    / "bundles"
    / "d53f0e.tmk"
)
PARTICIPANT_REF = "anon_0123456789abcdef"
SOURCE_READY_AT = "2026-09-04T18:00:00Z"


def _record_path(root: Path) -> Path:
    return root / f"2026-09-04-{PARTICIPANT_REF}.md"


def _write_mutated_record(
    path: Path,
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    text = path.read_text(encoding="utf-8")
    prefix, separator, remainder = text.partition("```json\n")
    assert separator
    payload, separator, suffix = remainder.partition("\n```\n")
    assert separator
    document = json.loads(payload)
    mutation(document)
    document["record_digest"] = sha256_hex(
        canonical_json_bytes(
            {key: value for key, value in document.items() if key != "record_digest"}
        )
    )
    path.write_text(
        prefix
        + "```json\n"
        + json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n```\n"
        + suffix,
        encoding="utf-8",
        newline="\n",
    )


def test_incomplete_pilot_record_round_trips_without_identifiers_or_rows(
    tmp_path: Path,
) -> None:
    record = create_pilot_session_record(
        participant_ref=PARTICIPANT_REF,
        source_ready_at=SOURCE_READY_AT,
        outcome="incomplete",
    )
    destination = _record_path(tmp_path)

    write_pilot_record(record, destination)

    assert load_pilot_record(destination) == record
    text = destination.read_text(encoding="utf-8")
    assert "source.csv" not in text
    assert "control_users" not in text
    assert "@" not in text
    assert record.measurements.completed_cycles.model_dump() == {
        "numerator": 0,
        "denominator": 1,
    }


@pytest.mark.parametrize(
    "mutation",
    [
        lambda document: document.__setitem__(
            "source_ready_at", "2026-09-04 18:00:00"
        ),
        lambda document: document.pop("measurements"),
        lambda document: document.__setitem__(
            "participant_ref", "alice@example.test"
        ),
        lambda document: document.__setitem__("outcome", "successful"),
    ],
    ids=(
        "malformed-timestamp",
        "missing-denominators",
        "raw-participant-identifier",
        "unsupported-outcome",
    ),
)
def test_pilot_record_validator_rejects_invalid_contracts(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    destination = _record_path(tmp_path)
    write_pilot_record(
        create_pilot_session_record(
            participant_ref=PARTICIPANT_REF,
            source_ready_at=SOURCE_READY_AT,
            outcome="incomplete",
        ),
        destination,
    )
    _write_mutated_record(destination, mutation)

    with pytest.raises(PilotRecordValidationError):
        load_pilot_record(destination)


def test_pilot_session_cli_creates_and_validates_record(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = _record_path(tmp_path)

    assert main(
        [
            "pilot-session",
            "create",
            "--participant-ref",
            PARTICIPANT_REF,
            "--source-ready-at",
            SOURCE_READY_AT,
            "--outcome",
            "incomplete",
            "--out",
            str(destination),
        ]
    ) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["valid"] is True
    assert created["record_digest"] == load_pilot_record(destination).record_digest

    assert main(["pilot-session", "validate", str(destination)]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated == created


def test_pilot_session_cli_rejects_public_benchmark_bundle(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = _record_path(tmp_path)

    assert main(
        [
            "pilot-session",
            "create",
            "--participant-ref",
            PARTICIPANT_REF,
            "--source-ready-at",
            SOURCE_READY_AT,
            "--bundle-ready-at",
            "2026-09-04T18:10:00Z",
            "--outcome",
            "completed",
            "--bundle",
            str(ASOS_BUNDLE),
            "--out",
            str(destination),
        ]
    ) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] is False
    assert result["error"]["code"] == "pilot_record_error"
    assert "external aggregate pilot" in result["error"]["message"]
    assert not destination.exists()
