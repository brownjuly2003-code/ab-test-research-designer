"""Deterministic frontend bundle budget (audit F-13).

Lighthouse's performance score varies run to run, so it stays a warning; what must
never drift silently is the shipped JavaScript weight. This gate fails the build
when the entry chunk or the total JS payload crosses an explicit budget, forcing a
conscious decision (code-split, drop a dependency, or raise the budget in review).

Budgets are raw (uncompressed) bytes of dist/assets/*.js:
- entry chunk (index-*.js): 512 000 bytes — 495 461 as of 2026-07-12;
- all chunks together:    1 150 000 bytes — 1 067 312 as of 2026-07-12.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DIST_ASSETS = ROOT_DIR / "app" / "frontend" / "dist" / "assets"

ENTRY_CHUNK_BUDGET_BYTES = 512_000
TOTAL_JS_BUDGET_BYTES = 1_150_000


def check_budget(assets_dir: Path) -> list[str]:
    """Return violations; empty means the budget holds."""
    chunks = sorted(assets_dir.glob("*.js"))
    if not chunks:
        return [f"no JS chunks found under {assets_dir} — did the frontend build run?"]

    errors: list[str] = []
    total = 0
    for chunk in chunks:
        size = chunk.stat().st_size
        total += size
        if chunk.name.startswith("index-") and size > ENTRY_CHUNK_BUDGET_BYTES:
            errors.append(
                f"entry chunk {chunk.name} is {size:,} bytes"
                f" (budget {ENTRY_CHUNK_BUDGET_BYTES:,})"
            )
    if total > TOTAL_JS_BUDGET_BYTES:
        errors.append(
            f"total JS payload is {total:,} bytes across {len(chunks)} chunk(s)"
            f" (budget {TOTAL_JS_BUDGET_BYTES:,})"
        )
    return errors


def self_test() -> int:
    with tempfile.TemporaryDirectory() as raw_dir:
        assets = Path(raw_dir)

        (assets / "index-abc.js").write_bytes(b"x" * 1024)
        (assets / "vendor-def.js").write_bytes(b"x" * 1024)
        if check_budget(assets):
            print("[bundle-budget] self-test FAILED: a within-budget build was flagged", file=sys.stderr)
            return 1

        (assets / "index-abc.js").write_bytes(b"x" * (ENTRY_CHUNK_BUDGET_BYTES + 1))
        violations = check_budget(assets)
        if not any("entry chunk" in violation for violation in violations):
            print("[bundle-budget] self-test FAILED: an oversized entry chunk was not flagged", file=sys.stderr)
            return 1

        (assets / "index-abc.js").write_bytes(b"x" * 1024)
        (assets / "vendor-def.js").write_bytes(b"x" * (TOTAL_JS_BUDGET_BYTES + 1))
        violations = check_budget(assets)
        if not any("total JS payload" in violation for violation in violations):
            print("[bundle-budget] self-test FAILED: an oversized total was not flagged", file=sys.stderr)
            return 1

    print("[bundle-budget] self-test passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-dir", default=str(DEFAULT_DIST_ASSETS))
    parser.add_argument("--self-test", action="store_true", help="Verify the detector flags oversized builds, then exit.")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    assets_dir = Path(args.assets_dir)
    violations = check_budget(assets_dir)
    if violations:
        for violation in violations:
            print(f"[bundle-budget] {violation}", file=sys.stderr)
        print(
            "[bundle-budget] over budget: split the chunk, drop the dependency, or raise the "
            "budget in scripts/check_bundle_budget.py as an explicit reviewed decision",
            file=sys.stderr,
        )
        return 1

    total = sum(chunk.stat().st_size for chunk in assets_dir.glob("*.js"))
    print(f"[bundle-budget] OK: {total:,} bytes of JS within budget ({TOTAL_JS_BUDGET_BYTES:,})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
