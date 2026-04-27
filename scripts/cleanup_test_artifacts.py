"""Remove test/build temp artifacts that accumulate locally.

Run from repo root: `python scripts/cleanup_test_artifacts.py`.

Targets (only deleted if they exist, dry-run with --dry-run):
- app/backend/tests/.tmp     legacy pytest temp from runs before
                             pytest.ini --basetemp landed
- .pytest_basetemp           current pytest basetemp (recreated next run)
- .tmp                        cxkm review sandbox
- .tmp_codex_ab_audit_pytest* leftover from external audit runs
- .coverage                   pytest-cov artifact at repo root
- site                        mkdocs build output
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

TARGETS: tuple[Path, ...] = (
    REPO_ROOT / "app" / "backend" / "tests" / ".tmp",
    REPO_ROOT / ".pytest_basetemp",
    REPO_ROOT / ".tmp",
    REPO_ROOT / ".coverage",
    REPO_ROOT / "site",
)

GLOB_TARGETS: tuple[str, ...] = (
    ".tmp_codex_ab_audit_pytest*",
)


def _human(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024  # type: ignore[assignment]
    return f"{size_bytes:.1f} TB"


def _dir_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                pass
    return total


def _resolve_targets() -> list[Path]:
    paths = [p for p in TARGETS if p.exists()]
    for pattern in GLOB_TARGETS:
        paths.extend(REPO_ROOT.glob(pattern))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, do not delete")
    args = parser.parse_args()

    paths = _resolve_targets()
    if not paths:
        print("nothing to clean — repo is already tidy")
        return 0

    total_freed = 0
    for path in paths:
        size = _dir_size(path)
        total_freed += size
        action = "would remove" if args.dry_run else "removing"
        print(f"{action}: {path.relative_to(REPO_ROOT)}  ({_human(size)})")
        if args.dry_run:
            continue
        try:
            if path.is_file():
                path.unlink()
            else:
                shutil.rmtree(path)
        except OSError as exc:
            print(f"  WARN: {exc}", file=sys.stderr)

    suffix = "would free" if args.dry_run else "freed"
    print(f"{suffix}: {_human(total_freed)} across {len(paths)} target(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
