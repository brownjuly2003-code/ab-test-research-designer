"""Sync smoke-generated screenshots from docs/demo/ to docs-site/assets/screenshots/.

`docs/demo/` is the single source of truth for screenshots produced by
`scripts/run_local_smoke.py` and referenced from the GitHub README via
`raw.githubusercontent.com` URLs.

mkdocs serves only files inside `docs_dir` (= `docs-site/`), so the docs
site needs its own copies. This script does that copy. Re-run it after
the smoke script regenerates `docs/demo/` and before `mkdocs build`.

Files unique to docs-site (e.g. comparison-distribution-view.png that
was added manually) are left alone.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "docs" / "demo"
TARGET = REPO_ROOT / "docs-site" / "assets" / "screenshots"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    if not SOURCE.is_dir():
        print(f"source missing: {SOURCE}", file=sys.stderr)
        return 1
    TARGET.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped_same = 0
    for src in sorted(SOURCE.glob("*.png")):
        dst = TARGET / src.name
        if dst.exists() and _sha256(dst) == _sha256(src):
            skipped_same += 1
            continue
        shutil.copy2(src, dst)
        copied += 1
        print(f"  copied: {src.name}")

    print(f"done: {copied} copied, {skipped_same} already in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
