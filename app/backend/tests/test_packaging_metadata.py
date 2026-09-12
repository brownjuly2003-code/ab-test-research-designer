"""Guard that runtime resources are declared in package-data or explicitly allowlisted.

A new non-Python file under ``app/backend/**`` must either be matched by a glob in
``[tool.setuptools.package-data]`` or added to the allowlist below with a reason.
This test reads ``pyproject.toml`` and the tracked inventory; it does not build a wheel.
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_PREFIX = "app/backend/"
_SKIP_WALK_DIRS = frozenset({"__pycache__", "data", ".tmp", "node_modules"})


def _load_pyproject() -> dict[str, Any]:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        payload = tomllib.load(handle)
    if not isinstance(payload, dict):
        pytest.fail("pyproject.toml did not parse as a table")
    return payload


def _setuptools_table(pyproject: dict[str, Any]) -> dict[str, Any]:
    tool = pyproject.get("tool")
    if not isinstance(tool, dict):
        return {}
    setuptools = tool.get("setuptools")
    if not isinstance(setuptools, dict):
        return {}
    return setuptools


def _as_str_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _backend_inventory() -> list[str]:
    """Tracked (or walked) paths under ``app/backend``, posix-relative to the repo."""
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=false", "ls-files", "app/backend"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except OSError:
        result = None
    if result is not None and result.returncode == 0:
        return [line.replace("\\", "/") for line in result.stdout.splitlines() if line]

    collected: list[str] = []
    backend_root = REPO_ROOT / "app" / "backend"
    for dirpath, dirnames, filenames in os.walk(backend_root):
        dirnames[:] = [name for name in dirnames if name not in _SKIP_WALK_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            collected.append(path.relative_to(REPO_ROOT).as_posix())
    return collected


def _covered_by_package_data(path: str, package_data: dict[str, Any]) -> bool:
    posix = PurePosixPath(path.replace("\\", "/"))
    for package, globs in package_data.items():
        package_dir = PurePosixPath(*str(package).split("."))
        try:
            relative = posix.relative_to(package_dir)
        except ValueError:
            continue
        for pattern in _as_str_list(globs):
            if relative.full_match(pattern):
                return True
    return False


def _allowlisted(path: str) -> bool:
    posix = path.replace("\\", "/")
    # Tests are not part of the distribution — review decision.
    if posix.startswith("app/backend/tests/"):
        return True
    parent, _, name = posix.rpartition("/")
    # requirements*.in / requirements*.txt are read only by git-gated dev tools
    # (evidence/public_pilot_abx.py:503, evidence/stats_kernel.py:297) that already
    # require a git checkout and do not work from an installed wheel. requirements.in
    # also ships as a side effect of [tool.setuptools.dynamic]; that is expected.
    if parent == "app/backend" and (
        fnmatch.fnmatch(name, "requirements*.in") or fnmatch.fnmatch(name, "requirements*.txt")
    ):
        return True
    # Other *.md under app/backend (schema documentation) are not needed at runtime.
    if posix.startswith(BACKEND_PREFIX) and posix.endswith(".md"):
        return True
    # Reserved (phase-G) modules and their pinned schemas are excluded from the
    # wheel on purpose; check_wheel_payload.py fails the build if one ships.
    if "/evidence/reserved/" in posix:
        return True
    return False


def test_non_python_backend_files_are_packaged_or_allowlisted() -> None:
    setuptools = _setuptools_table(_load_pyproject())
    package_data = setuptools.get("package-data")
    if not isinstance(package_data, dict):
        package_data = {}

    uncovered: list[str] = []
    for path in _backend_inventory():
        if path.endswith(".py"):
            continue
        if _covered_by_package_data(path, package_data) or _allowlisted(path):
            continue
        uncovered.append(path)

    if uncovered:
        formatted = "\n".join(f"  - {path}" for path in uncovered)
        pytest.fail(
            "non-Python files under app/backend must be covered by "
            "[tool.setuptools.package-data] or the explicit allowlist:\n"
            f"{formatted}"
        )


def test_setuptools_excludes_tests_and_runtime_data_packages() -> None:
    setuptools = _setuptools_table(_load_pyproject())
    find = setuptools.get("packages", {})
    if not isinstance(find, dict):
        find = {}
    find = find.get("find", {})
    if not isinstance(find, dict):
        find = {}
    exclude = _as_str_list(find.get("exclude"))
    missing = [
        item
        for item in ("app.backend.tests", "app.backend.tests.*", "app.backend.data")
        if item not in exclude
    ]
    assert missing == [], (
        "[tool.setuptools.packages.find] exclude must list tests and runtime data: "
        + ", ".join(missing)
    )


def test_exclude_package_data_blocks_sqlite() -> None:
    setuptools = _setuptools_table(_load_pyproject())
    exclude_package_data = setuptools.get("exclude-package-data")
    if not isinstance(exclude_package_data, dict):
        exclude_package_data = {}
    patterns = _as_str_list(exclude_package_data.get("*"))
    assert "*.sqlite3" in patterns, (
        '[tool.setuptools.exclude-package-data] "*" must include "*.sqlite3"'
    )
