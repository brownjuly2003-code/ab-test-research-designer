#!/usr/bin/env python
"""Wheel payload gate — runtime resources in, tests and secrets out.

Editable installs resolve ``__file__``-relative reads against the source tree, so
``pip install -e .`` cannot catch a missing package-data glob. This gate builds a
non-editable wheel and checks its namelist:

* required runtime resources present (ABX schemas, i18n catalogs, built-in
  YAML templates) — names taken from the filesystem;
* tests, sqlite databases, ``.env``, frontend sources, ``node_modules`` and the
  reserved (phase-G) modules absent.

Usage::

    python scripts/check_wheel_payload.py             # build a wheel, exit 1 on violations
    python scripts/check_wheel_payload.py --self-test # prove the detector works (no build)
"""

from __future__ import annotations

import argparse
import fnmatch
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Sequence
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
# The build needs no network with --no-build-isolation; a stall means something is
# wrong, so fail the check instead of burning the job-level timeout.
_BUILD_TIMEOUT_SEC = 300


def _posix(path: str) -> str:
    posix = path.replace("\\", "/")
    if posix.startswith("./"):
        posix = posix[2:]
    return posix.rstrip("/")


def forbidden_reason(member: str) -> str | None:
    """Return a human-readable reason if *member* must not ship, else ``None``."""
    posix = _posix(member)
    if not posix:
        return None
    parts = [part for part in posix.split("/") if part]
    name = parts[-1]
    if posix == "app/backend/tests" or posix.startswith("app/backend/tests/"):
        return "tests must not ship in the wheel"
    # Excluded in pyproject, asserted here: an exclude that stops matching is
    # silent, and the whole point of reserved/ is that it does not ship.
    if "reserved" in parts and "evidence" in parts:
        return "reserved (phase-G) modules must not ship in the wheel"
    if posix == "app/frontend" or posix.startswith("app/frontend/"):
        return "frontend sources must not ship in the wheel"
    if "node_modules" in parts:
        return "node_modules must not ship in the wheel"
    # fnmatchcase, not fnmatch: fnmatch folds case on Windows but not on Linux, so a
    # case-varied name would be caught locally and slip through on the CI runner.
    if fnmatch.fnmatchcase(name.lower(), "*.sqlite3*"):
        return "sqlite database must not ship in the wheel"
    if fnmatch.fnmatchcase(name.lower(), "*.env"):
        return "env file must not ship in the wheel"
    return None


def evaluate_payload(
    namelist: Sequence[str],
    required: Sequence[str],
) -> tuple[list[str], list[tuple[str, str]]]:
    """Return ``(missing_required, forbidden_members)`` for a wheel namelist."""
    names = {_posix(item) for item in namelist}
    missing = [path for path in required if _posix(path) not in names]
    forbidden: list[tuple[str, str]] = []
    for member in namelist:
        reason = forbidden_reason(member)
        if reason is not None:
            forbidden.append((member, reason))
    return missing, forbidden


def collect_required_payload_paths(repo_root: Path) -> tuple[list[str], list[str]]:
    """Discover runtime resource paths from the source tree.

    Returns ``(paths, errors)``. *errors* is non-empty when a required group
    has no files on disk (a silent empty glob would otherwise pass).
    """
    groups: tuple[tuple[str, Path, str], ...] = (
        ("ABX schemas", repo_root / "app" / "backend" / "app" / "evidence" / "contracts" / "schemas" / "abx" / "0.1", "*.json"),
        ("i18n catalogs", repo_root / "app" / "backend" / "app" / "i18n", "*.json"),
        ("built-in templates", repo_root / "app" / "backend" / "templates", "*.yaml"),
    )
    paths: list[str] = []
    errors: list[str] = []
    for label, directory, pattern in groups:
        found = sorted(
            path.relative_to(repo_root).as_posix()
            for path in directory.glob(pattern)
            if path.is_file()
        )
        if not found:
            errors.append(f"no {label} matched {directory.as_posix()}/{pattern}")
            continue
        paths.extend(found)
    return paths, errors


def _cleanup_setuptools_artifacts(repo_root: Path) -> None:
    build_dir = repo_root / "build"
    if build_dir.is_dir():
        shutil.rmtree(build_dir)
    for egg_info in repo_root.glob("*.egg-info"):
        if egg_info.is_dir():
            shutil.rmtree(egg_info)
        elif egg_info.is_file():
            egg_info.unlink()


def _build_wheel(repo_root: Path, wheel_dir: Path) -> Path:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "-w",
            str(wheel_dir),
            "-q",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=_BUILD_TIMEOUT_SEC,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(
            f"pip wheel failed with exit {proc.returncode}"
            + (f":\n{detail}" if detail else "")
        )
    wheels = sorted(wheel_dir.glob("*.whl"))
    if len(wheels) != 1:
        names = ", ".join(path.name for path in wheels) or "(none)"
        raise RuntimeError(f"expected exactly one wheel in {wheel_dir}, found: {names}")
    return wheels[0]


def self_test() -> int:
    """Prove the detector flags a missing resource and a forbidden extra."""
    required = [
        "app/backend/app/i18n/en.json",
        "app/backend/app/i18n/ru.json",
        "app/backend/templates/checkout_conversion.yaml",
        "app/backend/app/evidence/contracts/schemas/abx/0.1/manifest.schema.json",
    ]
    clean = [
        *required,
        "app/backend/app/evidence/cli.py",
        "app/backend/app/i18n/__init__.py",
        "trialmark-0.1.0.dist-info/METADATA",
        "trialmark-0.1.0.dist-info/entry_points.txt",
    ]
    failures: list[str] = []

    missing_target = required[0]
    missing_list = [name for name in clean if name != missing_target]
    missing, forbidden = evaluate_payload(missing_list, required)
    if missing_target not in missing:
        failures.append(f"FAILED to flag missing resource: {missing_target!r}")
    if forbidden:
        failures.append(f"FALSE POSITIVE forbidden on a missing-only namelist: {forbidden}")

    extras = [
        "app/backend/tests/test_packaging_metadata.py",
        "app/backend/data/projects.sqlite3",
        "app/backend/data/projects.sqlite3-wal",
        # Case-varied and non-dotfile spellings: fnmatch would fold case on Windows only.
        "app/backend/data/Projects.SQLITE3",
        ".env",
        "app/backend/staging.env",
        "app/frontend/package.json",
        "app/frontend/node_modules/leftpad/index.js",
        "node_modules/leftpad/index.js",
        "app/backend/app/evidence/reserved/legacy.py",
        "app/backend/app/evidence/reserved/contracts/schemas/dbt/manifest/v12.json",
    ]
    for extra in extras:
        missing, forbidden = evaluate_payload([*clean, extra], required)
        if missing:
            failures.append(f"FALSE POSITIVE missing when extra {extra!r} present: {missing}")
        if not any(path == extra for path, _reason in forbidden):
            failures.append(f"FAILED to flag forbidden path: {extra!r}")

    missing, forbidden = evaluate_payload(clean, required)
    if missing or forbidden:
        failures.append(
            f"FALSE POSITIVE on a clean namelist: missing={missing} forbidden={forbidden}"
        )

    # `.lstrip("./")` would turn `.env` into `env` and miss the file; keep that trap closed.
    if forbidden_reason(".env") is None:
        failures.append("FAILED to flag '.env' after posix normalisation")
    if forbidden_reason("app/backend/app/env.py") is not None:
        failures.append("FALSE POSITIVE on env.py (must not match .env)")

    if failures:
        print("[wheel-payload] self-test FAILED:", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(
        f"[wheel-payload] self-test passed "
        f"(1 missing flagged, {len(extras)} forbidden extras flagged, {len(clean)} clean)."
    )
    return 0


def check_built_wheel(repo_root: Path) -> int:
    required, collect_errors = collect_required_payload_paths(repo_root)
    if collect_errors:
        print("[wheel-payload] FAILED: required runtime files missing from the source tree:", file=sys.stderr)
        for line in collect_errors:
            print(f"  - {line}", file=sys.stderr)
        return 1

    try:
        with tempfile.TemporaryDirectory(prefix="wheel-payload-") as raw_tmp:
            wheel_path = _build_wheel(repo_root, Path(raw_tmp))
            with zipfile.ZipFile(wheel_path) as archive:
                namelist = archive.namelist()
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"[wheel-payload] FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        _cleanup_setuptools_artifacts(repo_root)

    missing, forbidden = evaluate_payload(namelist, required)
    if missing or forbidden:
        print(
            f"[wheel-payload] FAILED: {len(missing)} missing resource(s), "
            f"{len(forbidden)} forbidden path(s) in the built wheel:",
            file=sys.stderr,
        )
        for path in missing:
            print(f"  missing   {path}", file=sys.stderr)
        for path, reason in forbidden:
            print(f"  forbidden {path}  ({reason})", file=sys.stderr)
        print(
            "\nDeclare runtime files in [tool.setuptools.package-data] and keep tests, "
            "sqlite, .env, frontend, and node_modules out of the wheel.",
            file=sys.stderr,
        )
        return 1

    print(
        f"[wheel-payload] OK: {len(namelist)} wheel member(s), "
        f"{len(required)} required runtime resource(s) present, no tests/sqlite/.env/frontend leaks."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Verify the detector flags a missing resource and a forbidden extra, then exit.",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    return check_built_wheel(ROOT_DIR)


if __name__ == "__main__":
    raise SystemExit(main())
