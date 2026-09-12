from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BUNDLE = (
    REPO_ROOT
    / "app"
    / "backend"
    / "tests"
    / "fixtures"
    / "evidence"
    / "asos"
    / "bundles"
    / "d53f0e.tmk"
)

# Verifying a bundle reads a ZIP and checks digests. Not one of these can take
# part in that, and every one of them costs real seconds at a practitioner's
# prompt -- which is the whole argument for `verify` being a separate command
# from `run`.
FORBIDDEN_MODULES = (
    "duckdb",
    "psycopg",
    "app.backend.app.config",
    "app.backend.app.repository",
    "app.backend.app.evidence.binary_aggregate",
    "app.backend.app.evidence.data_sources",
    "app.backend.app.evidence.lifecycle_store",
    "app.backend.app.evidence.pilot_records",
    "app.backend.app.evidence.pipeline",
)

_PROBE = """
import json
import sys

from app.backend.app.evidence.cli import main

archive, forbidden, report = sys.argv[1], sys.argv[2].split(","), sys.argv[3]
exit_code = main(["verify", archive])
loaded = [name for name in forbidden if name in sys.modules]
with open(report, "w", encoding="utf-8") as handle:
    json.dump({"exit_code": exit_code, "loaded": loaded}, handle)
"""


def test_verify_loads_nothing_a_verification_could_use(tmp_path: Path) -> None:
    """A cold `verify` must not drag a database and a query engine in with it.

    The check has to run in a fresh interpreter: inside this test session every
    module in the list is already imported by something else, so `sys.modules`
    here would prove nothing.
    """

    report = tmp_path / "probe.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            _PROBE,
            str(BUNDLE),
            ",".join(FORBIDDEN_MODULES),
            str(report),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["exit_code"] == 0
    assert payload["loaded"] == []
