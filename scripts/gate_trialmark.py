"""The focused Trialmark gate: the evidence surface, in a wait a person tolerates.

`verify_all.py` stays the full gate and the only thing that can clear a push.
This one trades the rest of the backend suite, the production build and the
browser flows for a runtime short enough to run between edits, and covers what
an evidence-layer change can actually break: the evidence modules, the CLI that
drives them, the persisted routes that serve them, and the one frontend feature
that reads them.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_TESTS_DIR = ROOT_DIR / "app" / "backend" / "tests"
FRONTEND_DIR = ROOT_DIR / "app" / "frontend"
NPM_EXECUTABLE = "npm.cmd" if os.name == "nt" else "npm"

# Reported, never enforced: a loaded laptop is not a regression, and a gate
# that fails on wall-clock teaches people to re-run it until it passes.
TARGET_SECONDS = 180

# Globs are expanded here rather than handed to pytest, because only a POSIX
# shell would expand them and this gate has to behave the same on Windows.
TEST_PATTERNS = (
    "test_evidence_*.py",
    "test_persisted_*.py",
    "test_abx_cli.py",
    "test_binary_aggregate_pipeline.py",
    "test_cli_cold_start.py",
    "test_decision_role_source.py",
    "test_gate3.py",
    "test_pilot_records.py",
    "test_source_validate.py",
    "test_trialmark_bundle_contract.py",
)


def format_command(command: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(command)
    return " ".join(command)


def run_step(label: str, command: list[str], cwd: Path) -> float:
    print(f"[gate] {label}: {format_command(command)}", flush=True)
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=cwd, check=False)
    elapsed = time.perf_counter() - started
    outcome = "ok" if completed.returncode == 0 else "FAILED"
    print(f"[gate] {label}: {outcome} in {elapsed:.1f}s", flush=True)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    return elapsed


def backend_test_paths() -> list[str]:
    selected: list[str] = []
    for pattern in TEST_PATTERNS:
        matched = sorted(BACKEND_TESTS_DIR.glob(pattern))
        if not matched:
            # A renamed or deleted file must break the gate loudly. Silently
            # testing less than the list claims is the failure mode that makes
            # a focused gate worthless.
            raise SystemExit(f"[gate] no test file matches {pattern}")
        selected.extend(path.relative_to(ROOT_DIR).as_posix() for path in matched)
    return list(dict.fromkeys(selected))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Skip the TypeScript and Vitest steps even if dependencies exist.",
    )
    arguments = parser.parse_args()

    elapsed: dict[str, float] = {}
    elapsed["lint"] = run_step(
        "backend lint (ruff)",
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "app/backend/app",
            "app/backend/tests",
            "scripts",
        ],
        ROOT_DIR,
    )
    elapsed["types"] = run_step(
        "backend type check (mypy --strict)",
        [sys.executable, "-m", "mypy"],
        ROOT_DIR,
    )
    elapsed["tests"] = run_step(
        "evidence tests",
        [sys.executable, "-m", "pytest", "-q", *backend_test_paths()],
        ROOT_DIR,
    )

    if arguments.skip_frontend:
        print("[gate] frontend: skipped by --skip-frontend", flush=True)
    elif not (FRONTEND_DIR / "node_modules").exists():
        # A checkout without frontend dependencies should report an honest
        # gap, not fail; the full gate makes the same allowance.
        print("[gate] frontend: skipped, app/frontend/node_modules is absent", flush=True)
    else:
        # `npm --prefix <dir> run <script>` runs with the package directory as
        # cwd; `npm --prefix <dir> exec` does not.
        elapsed["typecheck"] = run_step(
            "frontend type check (tsc)",
            [NPM_EXECUTABLE, "--prefix", str(FRONTEND_DIR), "run", "typecheck"],
            ROOT_DIR,
        )
        elapsed["preflight"] = run_step(
            "frontend preflight unit tests (vitest)",
            [
                NPM_EXECUTABLE,
                "--prefix",
                str(FRONTEND_DIR),
                "run",
                "test:unit",
                "--",
                "src/features/preflight",
            ],
            ROOT_DIR,
        )

    total = sum(elapsed.values())
    breakdown = ", ".join(f"{name} {value:.1f}s" for name, value in elapsed.items())
    print(f"[gate] passed in {total:.1f}s ({breakdown})", flush=True)
    if total > TARGET_SECONDS:
        print(
            f"[gate] note: over the {TARGET_SECONDS}s target. Not a failure -- "
            "check whether the machine was busy before treating it as one.",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
