from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from app.backend.app.evidence.preflight import (
    AssignmentHealthIntervention,
    AssignmentHealthProfile,
    ObservedTelemetryProfile,
    ObservedTelemetrySchemaVersion,
    ProtocolPreflightReport,
    preflight_assignment_health,
    preflight_observed_telemetry,
    preflight_protocol,
)
from app.backend.app.evidence.protocol_io import load_protocol
from app.backend.app.evidence.public_pilots import load_asos_public_pilot

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_ROOT = Path(__file__).resolve().parent
PROTOCOL_PATH = DEMO_ROOT / "protocol.yaml"
ASOS_SOURCE = (
    REPO_ROOT
    / "app"
    / "backend"
    / "tests"
    / "fixtures"
    / "evidence"
    / "asos"
    / "d53f0e.parquet"
)
_ASOS_SCHEMA_VERSIONS = (
    ObservedTelemetrySchemaVersion(
        event_type="aggregate_assignment",
        version="benchmark-v1",
    ),
    ObservedTelemetrySchemaVersion(
        event_type="aggregate_metric_checkpoint",
        version="benchmark-v1",
    ),
)


class DemoError(RuntimeError):
    """Raised when the deterministic demo contract is not met."""


def _finding_codes(report: ProtocolPreflightReport) -> list[str]:
    return [finding.code for finding in report.findings]


def _require_fault(
    name: str,
    report: ProtocolPreflightReport,
    expected_code: str,
) -> list[str]:
    codes = _finding_codes(report)
    if report.ready or codes != [expected_code]:
        raise DemoError(
            f"{name} must block only with {expected_code}; observed {codes or ['ready']}"
        )
    return codes


def run_injected_fault_suite(
    protocol_path: Path = PROTOCOL_PATH,
    source_path: Path = ASOS_SOURCE,
) -> dict[str, list[str]]:
    """Run three isolated aggregate-only fault scenarios against the ASOS fixture."""

    protocol = load_protocol(protocol_path)
    pilot = load_asos_public_pilot(
        source_path,
        expected_experiment_id="d53f0e",
    )
    snapshot = next(item for item in pilot.snapshots if item.metric_id == 1)

    bad_metric = copy.deepcopy(protocol)
    bad_metrics = cast(dict[str, list[dict[str, Any]]], bad_metric["metrics"])
    bad_metrics["guardrails"].append(copy.deepcopy(bad_metrics["primary"][0]))
    bad_decision = cast(dict[str, Any], bad_metric["decision"])
    bad_harm_rules = cast(list[dict[str, Any]], bad_decision["harm_rules"])
    bad_harm_rules.append(
        {
            "code": "DEMO_METRIC_HARM",
            "metric_id": "metric_asos_1",
            "operator": "gt",
            "threshold": 1,
        }
    )
    bad_metric_report = preflight_protocol(bad_metric)

    seed_imbalance = copy.deepcopy(protocol)
    seed_interventions = cast(list[dict[str, Any]], seed_imbalance["interventions"])
    seed_protocol_report = preflight_protocol(seed_imbalance)
    if not seed_protocol_report.ready:
        raise DemoError("seed imbalance injection made the protocol incomplete")
    seed_analysis = cast(dict[str, Any], seed_imbalance["analysis"])
    observed_total = snapshot.count_c + snapshot.count_t
    skewed_control_count = round(observed_total * 0.9)
    skewed_counts = (skewed_control_count, observed_total - skewed_control_count)
    seed_profile = AssignmentHealthProfile(
        protocol_digest=seed_protocol_report.protocol_digest,
        random_seed=cast(int, seed_analysis["random_seed"]),
        synthetic_sample_size=100_000,
        interventions=tuple(
            AssignmentHealthIntervention(
                intervention_id=cast(str, intervention["intervention_id"]),
                allocation=cast(str, intervention["allocation"]),
                namespace=cast(str, intervention["namespace"]),
                hash_version=cast(str, intervention["hash_version"]),
                observed_count=skewed_counts[index],
            )
            for index, intervention in enumerate(seed_interventions)
        ),
    )
    seed_report = preflight_assignment_health(seed_imbalance, seed_profile)

    late_profile = ObservedTelemetryProfile(
        outcome_before_exposure_count=0,
        duplicate_event_count=0,
        unlinked_subject_count=0,
        events_beyond_max_lateness_count=1,
        schema_versions=_ASOS_SCHEMA_VERSIONS,
    )
    late_report = preflight_observed_telemetry(protocol, late_profile)

    return {
        "bad_metric": _require_fault(
            "bad_metric",
            bad_metric_report,
            "METRIC_ROLE_CONFLICT",
        ),
        "seed_imbalance": _require_fault(
            "seed_imbalance",
            seed_report,
            "ASSIGNMENT_SAMPLE_RATIO_MISMATCH",
        ),
        "late_exposure": _require_fault(
            "late_exposure",
            late_report,
            "TELEMETRY_MAX_LATENESS_EXCEEDED",
        ),
    }


def _run_cli(
    arguments: list[str],
    *,
    environment: dict[str, str],
    expected_returncode: int = 0,
) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "-m", "app.backend.app.evidence.cli", *arguments],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=120,
    )
    if completed.returncode != expected_returncode:
        detail = completed.stdout.strip() or completed.stderr.strip() or "no output"
        raise DemoError(
            f"Trialmark CLI returned {completed.returncode}, expected "
            f"{expected_returncode}: {detail}"
        )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise DemoError("Trialmark CLI did not emit one JSON result") from exc
    if not isinstance(result, dict):
        raise DemoError("Trialmark CLI result must be a JSON object")
    return cast(dict[str, Any], result)


def run_demo(output_dir: Path) -> dict[str, Any]:
    """Block the injected faults, then execute corrected run -> decision -> verify."""

    output_dir.mkdir(parents=True, exist_ok=True)
    analysis_archive = output_dir / "analysis.tmk"
    decision_archive = output_dir / "decision.tmk"
    tampered_archive = output_dir / "decision-tampered.tmk"
    database_path = output_dir / "trialmark.sqlite3"
    artifact_root = output_dir / "artifacts"
    occupied = [
        path
        for path in (
            analysis_archive,
            decision_archive,
            tampered_archive,
            database_path,
            artifact_root,
        )
        if path.exists()
    ]
    if occupied:
        raise DemoError(
            "output directory must be fresh; existing paths: "
            + ", ".join(path.name for path in occupied)
        )

    faults = run_injected_fault_suite()
    environment = os.environ.copy()
    environment.pop("AB_DATABASE_URL", None)
    environment["AB_DB_PATH"] = str(database_path)

    analysis = _run_cli(
        [
            "run",
            "--protocol",
            str(PROTOCOL_PATH),
            "--source",
            str(ASOS_SOURCE),
            "--actor",
            "demo-analyst",
            "--artifact-root",
            str(artifact_root),
            "--out",
            str(analysis_archive),
        ],
        environment=environment,
    )
    if analysis.get("valid") is not True:
        raise DemoError("corrected analysis bundle did not verify")
    run_id = analysis.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise DemoError("corrected analysis did not return a run_id")

    decision = _run_cli(
        [
            "decide",
            "--run",
            run_id,
            "--verdict",
            "ship",
            "--rationale",
            "ASOS preflight is clear and the bundle verifies.",
            "--actor",
            "demo-reviewer",
            "--artifact-root",
            str(artifact_root),
            "--out",
            str(decision_archive),
        ],
        environment=environment,
    )
    verification = _run_cli(
        ["verify", str(decision_archive), "--offline", "--policy", "strict"],
        environment=environment,
    )
    if decision != verification or verification.get("valid") is not True:
        raise DemoError("decision bundle verification did not match publication")

    shutil.copyfile(decision_archive, tampered_archive)
    with tampered_archive.open("ab") as archive:
        archive.write(b"X")
    tamper_verification = _run_cli(
        ["verify", str(tampered_archive), "--offline", "--policy", "strict"],
        environment=environment,
        expected_returncode=1,
    )
    tamper_verdicts = cast(
        dict[str, str], tamper_verification.get("verdicts", {})
    )
    tamper_errors = cast(
        list[dict[str, Any]], tamper_verification.get("errors", [])
    )
    if (
        tamper_verification.get("valid") is not False
        or tamper_verdicts.get("integrity") != "fail"
        or [error.get("code") for error in tamper_errors]
        != ["archive_trailing_bytes"]
    ):
        raise DemoError("tampered decision bundle did not fail strict verification")

    return {
        "faults": faults,
        "analysis": analysis,
        "decision": decision,
        "verification": verification,
        "tamper_verification": tamper_verification,
        "output_dir": str(output_dir.resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the deterministic five-minute Trialmark ASOS demo."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = run_demo(args.output_dir)
    except DemoError as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
