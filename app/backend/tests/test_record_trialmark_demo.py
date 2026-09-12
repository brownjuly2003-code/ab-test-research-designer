from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.backend.app.evidence.lifecycle_store import LifecycleEvidenceRunStore
from app.backend.app.evidence.stats_kernel import StatsKernelBuild
from app.backend.app.repository import ProjectRepository
from scripts.record_trialmark_demo import (
    DemoRecordingError,
    DemoRunSelection,
    _capture_poster,
    seed_recording_blocked_run,
    select_demo_runs,
)

_TEST_BUILD = StatsKernelBuild(
    git_commit="a" * 40,
    build_digest="sha256:"
    + hashlib.sha256(b"record-trialmark-demo-test-build").hexdigest(),
    dependency_lock_digest="sha256:"
    + hashlib.sha256(b"record-trialmark-demo-test-lock").hexdigest(),
)


@pytest.fixture(autouse=True)
def _stable_stats_kernel_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.backend.app.evidence.pipeline.load_stats_kernel_build",
        lambda: _TEST_BUILD,
    )


def test_select_demo_runs_uses_real_blocked_and_succeeded_analysis_states() -> None:
    portfolio = {
        "runs": [
            {"run_id": "run_decision", "kind": "decision", "status": "succeeded"},
            {"run_id": "run_ready", "kind": "analysis", "status": "succeeded"},
            {"run_id": "run_blocked", "kind": "preflight", "status": "succeeded"},
        ]
    }
    details: dict[str, dict[str, Any]] = {
        "run_decision": {"findings": []},
        "run_ready": {"findings": [], "estimates": [{"estimate_id": "estimate_1"}]},
        "run_blocked": {
            "findings": [
                {"finding_id": "finding_1", "state": "open"},
            ],
            "estimates": [],
        },
    }

    assert select_demo_runs(portfolio, details) == DemoRunSelection(
        blocked_run_id="run_blocked",
        analysis_run_id="run_ready",
    )


def test_select_demo_runs_fails_when_the_seed_has_no_blocked_run() -> None:
    portfolio = {
        "runs": [
            {"run_id": "run_ready", "kind": "analysis", "status": "succeeded"},
        ]
    }
    details: dict[str, dict[str, Any]] = {
        "run_ready": {"findings": [], "estimates": [{"estimate_id": "estimate_1"}]},
    }

    with pytest.raises(DemoRecordingError, match="blocked ASOS run"):
        select_demo_runs(portfolio, details)


def test_select_demo_runs_prefers_the_explicit_recording_blocker() -> None:
    portfolio = {
        "runs": [
            {"run_id": "run_other", "kind": "preflight", "status": "succeeded"},
            {"run_id": "run_recording", "kind": "preflight", "status": "succeeded"},
            {"run_id": "run_ready", "kind": "analysis", "status": "succeeded"},
        ]
    }
    details: dict[str, dict[str, Any]] = {
        "run_other": {"findings": [{"state": "open"}], "estimates": []},
        "run_recording": {"findings": [{"state": "open"}], "estimates": []},
        "run_ready": {"findings": [], "estimates": [{"estimate_id": "estimate_1"}]},
    }

    assert select_demo_runs(
        portfolio,
        details,
        preferred_blocked_run_id="run_recording",
    ) == DemoRunSelection(
        blocked_run_id="run_recording",
        analysis_run_id="run_ready",
    )


def test_capture_poster_returns_to_the_workbench_hero(tmp_path: Path) -> None:
    page = MagicMock()
    poster_path = tmp_path / "poster.png"

    _capture_poster(page, poster_path)

    page.evaluate.assert_called_once_with(
        "window.scrollTo({ top: 0, left: 0, behavior: 'instant' })"
    )
    page.screenshot.assert_called_once_with(
        path=str(poster_path),
        animations="disabled",
    )


def test_seed_recording_blocked_run_persists_real_preflight_finding(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "recording.sqlite3"
    artifact_root = tmp_path / ".trialmark" / "artifacts"
    repository = ProjectRepository(f"sqlite:///{database_path.as_posix()}")
    try:
        run = seed_recording_blocked_run(
            repository,
            artifact_root=artifact_root,
        )

        assert run.kind == "preflight"
        assert run.status == "succeeded"
        assert "TELEMETRY_EVENT_SCHEMA_MISSING" in {
            json.loads(artifact.payload)["code"]
            for artifact in run.artifacts
            if artifact.role == "finding"
        }
        assert LifecycleEvidenceRunStore(repository, artifact_root).get(run.run_id) == run
    finally:
        repository.close()


def test_recorder_help_runs_from_the_repository_root() -> None:
    repository_root = Path(__file__).resolve().parents[3]

    result = subprocess.run(
        [sys.executable, "scripts/record_trialmark_demo.py", "--help"],
        cwd=repository_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "Record the real Trialmark ASOS workbench flow" in result.stdout
