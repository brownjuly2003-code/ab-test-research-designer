"""Deterministic frontend bundle budget (audit F-13 / plan step 8).

Lighthouse's performance score varies run to run, so it stays a warning; what must
never drift silently is the shipped JavaScript weight. This gate fails the build
when the entry chunk or the total JS payload crosses an explicit budget, forcing a
conscious decision (code-split, drop a dependency, or raise the budget via ADR).

Hard budgets are raw (uncompressed) bytes of dist/assets/*.js:
- entry chunk (index-*.js): 512 000 bytes
- all chunks together:    1 150 000 bytes

Reporting (non-failing) includes per-chunk raw sizes and total gzip size so
reviews can see headroom and transfer weight without raising the hard ceiling.
Raising ENTRY_CHUNK_BUDGET_BYTES or TOTAL_JS_BUDGET_BYTES requires an ADR under
docs/adr/ — never as a side effect of landing a feature (see CONTRIBUTING).
"""

from __future__ import annotations

import argparse
import gzip
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DIST_ASSETS = ROOT_DIR / "app" / "frontend" / "dist" / "assets"

ENTRY_CHUNK_BUDGET_BYTES = 512_000
TOTAL_JS_BUDGET_BYTES = 1_150_000
# Soft headroom signal: below this fraction of the total budget, print a warning.
HEADROOM_WARN_FRACTION = 0.05


def _gzip_size(path: Path) -> int:
    return len(gzip.compress(path.read_bytes(), compresslevel=9, mtime=0))


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


def report_chunks(assets_dir: Path) -> tuple[int, int, list[tuple[str, int, int]]]:
    """Return (total_raw, total_gzip, [(name, raw, gzip), ...]) sorted by raw desc."""
    rows: list[tuple[str, int, int]] = []
    total_raw = 0
    total_gzip = 0
    for chunk in assets_dir.glob("*.js"):
        raw = chunk.stat().st_size
        gz = _gzip_size(chunk)
        rows.append((chunk.name, raw, gz))
        total_raw += raw
        total_gzip += gz
    rows.sort(key=lambda item: item[1], reverse=True)
    return total_raw, total_gzip, rows


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

        total_raw, total_gzip, rows = report_chunks(assets)
        if total_raw <= 0 or total_gzip <= 0 or not rows:
            print("[bundle-budget] self-test FAILED: per-chunk/gzip report empty", file=sys.stderr)
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
            "budget in scripts/check_bundle_budget.py only with a new ADR under docs/adr/",
            file=sys.stderr,
        )
        return 1

    total_raw, total_gzip, rows = report_chunks(assets_dir)
    headroom = TOTAL_JS_BUDGET_BYTES - total_raw
    headroom_pct = (headroom / TOTAL_JS_BUDGET_BYTES) * 100 if TOTAL_JS_BUDGET_BYTES else 0.0

    print(
        f"[bundle-budget] OK: {total_raw:,} raw / {total_gzip:,} gzip bytes of JS "
        f"within budget ({TOTAL_JS_BUDGET_BYTES:,} raw); "
        f"headroom {headroom:,} ({headroom_pct:.1f}%)"
    )
    print("[bundle-budget] per-chunk (raw / gzip):")
    for name, raw, gz in rows:
        marker = " entry" if name.startswith("index-") else ""
        print(f"  {name}: {raw:,} / {gz:,}{marker}")

    if headroom_pct < HEADROOM_WARN_FRACTION * 100:
        print(
            f"[bundle-budget] WARNING: headroom under {HEADROOM_WARN_FRACTION:.0%} — "
            "prefer code-split/deps cleanup before any budget raise (ADR required).",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
