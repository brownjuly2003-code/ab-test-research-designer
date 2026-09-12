from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.generate_method_profile_table import update_readme

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_readme_method_profile_table_is_generated_and_current() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert update_readme(readme) == readme
    assert "<!-- method-profile-table:start -->" in readme
    assert "`binary_pooled_z_newcombe`" in readme


def test_method_profile_readme_script_runs_from_repo_root() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate_method_profile_table.py"),
            "--check",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
