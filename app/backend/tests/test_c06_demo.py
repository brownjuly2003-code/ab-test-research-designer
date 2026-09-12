from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import sys
import traceback
import zipfile
from collections.abc import Mapping
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from app.backend.app.config import get_settings
from app.backend.app.evidence.abx import verify_bundle
from app.backend.app.evidence.cli import main as trialmark_cli_main
from app.backend.app.evidence.stats_kernel import StatsKernelBuild
from examples.demo.run_demo import DemoError, run_demo, run_injected_fault_suite

REPO_ROOT = Path(__file__).resolve().parents[3]

_TEST_BUILD = StatsKernelBuild(
    git_commit="a" * 40,
    build_digest="sha256:" + hashlib.sha256(b"c06-demo-test-build").hexdigest(),
    dependency_lock_digest="sha256:"
    + hashlib.sha256(b"c06-demo-test-lock").hexdigest(),
)


def _in_process_run_cli(
    arguments: list[str],
    *,
    environment: Mapping[str, str],
    expected_returncode: int = 0,
) -> dict[str, Any]:
    """Run the demo CLI in-process so a patched StatsKernelBuild is visible.

    Translate ``SystemExit`` into a returncode so a mismatch raises
    ``DemoError`` with captured output, matching subprocess ``_run_cli``
    instead of leaking a bare ``SystemExit``. Integer codes are preserved;
    ``None`` (bare ``sys.exit()``) is 0; any other non-integer code is 1
    with the message printed to the captured stderr. Any other exception
    prints its traceback to the captured stderr and becomes returncode 1,
    matching a crashed subprocess. The subprocess ``timeout=120`` bound is
    not reproduced for the in-process call. ``environment`` is snapshotted
    before the process env is replaced, so a live ``os.environ`` (or any
    mapping aliased to it) is not emptied by ``clear()``. Env and the
    settings cache are restored even if returning to the original cwd
    raises ``OSError``.
    """

    environment = dict(environment)
    saved_cwd = Path.cwd()
    saved_env = os.environ.copy()
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        os.environ.clear()
        os.environ.update(environment)
        os.chdir(REPO_ROOT)
        get_settings.cache_clear()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                returncode = trialmark_cli_main(arguments)
            except SystemExit as exc:
                if isinstance(exc.code, int):
                    returncode = exc.code
                elif exc.code is None:
                    returncode = 0
                else:
                    returncode = 1
                    print(exc.code, file=sys.stderr)
            except Exception:
                traceback.print_exc()
                returncode = 1
    finally:
        os.environ.clear()
        os.environ.update(saved_env)
        get_settings.cache_clear()
        try:
            os.chdir(saved_cwd)
        except OSError:
            pass

    if returncode != expected_returncode:
        detail = stdout.getvalue().strip() or stderr.getvalue().strip() or "no output"
        raise DemoError(
            f"Trialmark CLI returned {returncode}, expected "
            f"{expected_returncode}: {detail}"
        )
    try:
        result = json.loads(stdout.getvalue())
    except json.JSONDecodeError as exc:
        raise DemoError("Trialmark CLI did not emit one JSON result") from exc
    if not isinstance(result, dict):
        raise DemoError("Trialmark CLI result must be a JSON object")
    return result


@pytest.fixture(autouse=True)
def _stable_stats_kernel_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.backend.app.evidence.pipeline.load_stats_kernel_build",
        lambda: _TEST_BUILD,
    )


def test_injected_asos_faults_are_blocking_and_specific() -> None:
    assert run_injected_fault_suite() == {
        "bad_metric": ["METRIC_ROLE_CONFLICT"],
        "seed_imbalance": ["ASSIGNMENT_SAMPLE_RATIO_MISMATCH"],
        "late_exposure": ["TELEMETRY_MAX_LATENESS_EXCEEDED"],
    }


def test_corrected_demo_runs_to_a_verified_human_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # run_demo shells out to `python -m app.backend.app.evidence.cli`; keep that
    # path in-process so the StatsKernelBuild fixture actually reaches
    # load_stats_kernel_build. The injected-fault suite calls the preflight
    # functions directly and never invokes the CLI, so it is unaffected by this
    # patch. This slice no longer covers the successful end-to-end path through
    # a real CLI process; that is a deliberate trade for independence from
    # git-tree state (a test cannot be both a subprocess and independent of
    # tree cleanliness). Remaining subprocess coverage is
    # test_recorder_help_runs_from_the_repository_root and error paths.
    monkeypatch.setattr("examples.demo.run_demo._run_cli", _in_process_run_cli)
    summary = run_demo(tmp_path)
    analysis_archive = tmp_path / "analysis.tmk"
    decision_archive = tmp_path / "decision.tmk"
    tampered_archive = tmp_path / "decision-tampered.tmk"

    assert summary["faults"] == run_injected_fault_suite()
    assert summary["analysis"]["valid"] is True
    assert summary["analysis"]["verdicts"]["lineage"] == "pass"
    assert summary["decision"]["valid"] is True
    assert summary["verification"] == verify_bundle(decision_archive)
    assert summary["tamper_verification"]["valid"] is False
    assert summary["tamper_verification"]["verdicts"]["integrity"] == "fail"
    assert [
        error["code"] for error in summary["tamper_verification"]["errors"]
    ] == ["archive_trailing_bytes"]
    assert analysis_archive.is_file()
    assert decision_archive.is_file()
    assert tampered_archive.is_file()

    with zipfile.ZipFile(decision_archive) as archive:
        envelope = json.loads(archive.read("decision/statement.dsse.json"))
    statement = json.loads(base64.b64decode(envelope["payload"], validate=True))
    decision = statement["predicate"]
    assert statement["subject"][0]["digest"]["sha256"] == summary["analysis"][
        "bundle_id"
    ].removeprefix("sha256:")
    assert decision["human_verdict"] == "ship"
    assert decision["decided_by"]["actor_ref"] == "demo-reviewer"
    assert decision["rationale"] == "ASOS preflight is clear and the bundle verifies."


def test_five_minute_demo_entrypoints_are_documented() -> None:
    shell = (REPO_ROOT / "examples" / "demo" / "run_demo.sh").read_text(
        encoding="utf-8"
    )
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    article = (
        REPO_ROOT / "docs" / "article" / "trialmark-asos-tamper-demo.md"
    ).read_text(encoding="utf-8")

    assert shell.startswith("#!/usr/bin/env sh\nset -eu\n")
    assert "examples/demo/run_demo.py" in shell
    assert "bash examples/demo/run_demo.sh" in readme
    assert "docs/article/trialmark-asos-tamper-demo.md" in readme
    assert "python -m examples.demo.run_demo --output-dir" in article
    assert "decision-tampered.tmk" in article
