from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.backend.app.evidence import cli
from app.backend.app.evidence.cli import main

REPO_ROOT = Path(__file__).resolve().parents[3]
PILOT_PROTOCOL = REPO_ROOT / "examples" / "pilot" / "protocol.yaml"
PILOT_SOURCE = REPO_ROOT / "examples" / "pilot" / "aggregate.csv"

AGGREGATE_HEADER = (
    "control_users,control_conversions,treatment_users,treatment_conversions\n"
)


def _validate(
    capsys: pytest.CaptureFixture[str],
    *,
    protocol: Path = PILOT_PROTOCOL,
    source: Path = PILOT_SOURCE,
) -> tuple[int, dict[str, object]]:
    exit_code = main(
        ["source", "validate", "--protocol", str(protocol), "--source", str(source)]
    )
    return exit_code, json.loads(capsys.readouterr().out)


def _protocol_without_digest_match(tmp_path: Path) -> Path:
    """The README protocol with its source metric redefined under it.

    Changing the definition changes what the source hashes to, so the
    `definition_digest` the protocol froze no longer describes it -- the drift
    the digest exists to catch.
    """

    text = PILOT_PROTOCOL.read_text(encoding="utf-8")
    replaced = text.replace(
        "        numerator: converted_subjects\n",
        "        numerator: checked_out_subjects\n",
    )
    assert replaced != text
    destination = tmp_path / "protocol.yaml"
    destination.write_text(replaced, encoding="utf-8")
    return destination


def test_source_validate_accepts_the_documented_readme_pair(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, payload = _validate(capsys)

    assert exit_code == 0
    assert payload["valid"] is True
    assert payload["metric_id"] == "metric_checkout_conversion"
    assert payload["source_ref"] == "pilot_source_alpha"
    assert payload["evidence_type"] == "external_pilot"
    assert payload["aggregate"] == {
        "control_users": 1000,
        "control_conversions": 100,
        "treatment_users": 1200,
        "treatment_conversions": 144,
    }


def test_source_validate_names_both_schemas_for_a_row_level_export(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "row_level.csv"
    source.write_text(
        "unit_id,variant,converted\nu1,control,0\nu2,treatment,1\n",
        encoding="utf-8",
    )

    exit_code, payload = _validate(capsys, source=source)

    assert exit_code == 1
    assert payload["valid"] is False
    error = payload["error"]
    assert isinstance(error, dict)
    assert error["code"] == "source_invalid"
    message = error["message"]
    assert isinstance(message, str)
    # The point of the slice: the reader can fix their file from this line
    # alone, without opening the documentation.
    assert "expected control_users BIGINT" in message
    assert "found unit_id VARCHAR" in message


def test_source_validate_rejects_more_than_one_aggregate_row(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "two_rows.csv"
    source.write_text(
        AGGREGATE_HEADER + "1000,100,1200,144\n900,90,1100,130\n",
        encoding="utf-8",
    )

    exit_code, payload = _validate(capsys, source=source)

    assert exit_code == 1
    error = payload["error"]
    assert isinstance(error, dict)
    message = error["message"]
    assert isinstance(message, str)
    assert "exactly one aggregate row, found 2" in message
    assert "row-level export" in message


def test_source_validate_reports_a_metric_the_protocol_never_froze(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, payload = _validate(
        capsys,
        protocol=_protocol_without_digest_match(tmp_path),
    )

    assert exit_code == 1
    error = payload["error"]
    assert isinstance(error, dict)
    assert error["code"] == "source_invalid"
    message = error["message"]
    assert isinstance(message, str)
    assert "definition digest does not match the protocol" in message
    # Both sides, so the reader can tell which one they meant to change.
    assert message.count("sha256:") == 2


def test_source_validate_refuses_a_protocol_without_an_aggregate_binary_source(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    text = PILOT_PROTOCOL.read_text(encoding="utf-8")
    marker = "  trialmark.aggregate-binary:"
    head, separator, _ = text.partition(marker)
    assert separator
    protocol = tmp_path / "protocol.yaml"
    protocol.write_text(head.replace("extensions:\n", "extensions: {}\n"), "utf-8")

    exit_code, payload = _validate(capsys, protocol=protocol)

    assert exit_code == 1
    error = payload["error"]
    assert isinstance(error, dict)
    assert error["code"] in {"source_invalid", "configuration_error"}


def test_source_validate_opens_no_repository_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The slice's whole promise: a pre-flight that cannot touch state."""

    def _refuse() -> object:
        raise AssertionError("source validate must not open a repository")

    monkeypatch.setattr(cli, "_create_repository", _refuse)
    monkeypatch.setenv("AB_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.chdir(tmp_path)

    exit_code, payload = _validate(capsys)

    assert exit_code == 0
    assert payload["valid"] is True
    assert list(tmp_path.iterdir()) == []
