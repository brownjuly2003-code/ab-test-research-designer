#!/usr/bin/env python
"""Repo hygiene gate — keep internal-only docs out of the public tree.

The 2026-06-17 audit untracked two classes of file that should never live in
the public repository again:

* ``archive/**`` — internal planning docs, landed CX specs, and smoke/verify
  run artifacts. Useful locally, noise (and a presentation hit) in public.
* root ``audit_*.md`` — internal audit reports (``audit_opus_*.md``,
  ``audit_kimi_*.md``, ``audit_codex_*.md``, etc.).

Both are ignored via ``.gitignore`` now, but ``git add -f`` or a future
``.gitignore`` edit could silently re-introduce them. This gate fails CI the
moment any such path shows up in ``git ls-files``, so the cleanup can't rot.

Usage::

    python scripts/check_repo_hygiene.py             # scan tracked files, exit 1 on violations
    python scripts/check_repo_hygiene.py --self-test # prove the detector works
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def classify(path: str) -> str | None:
    """Return a human-readable reason if *path* is forbidden, else ``None``.

    ``path`` is a forward-slash repo-relative path exactly as ``git ls-files``
    emits it.
    """
    if path == "archive" or path.startswith("archive/"):
        return "internal archive/ doc or run artifact"
    if "/" not in path and path.startswith("audit_") and path.endswith(".md"):
        return "internal root-level audit report"
    return None


def find_violations(paths: list[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for path in paths:
        reason = classify(path)
        if reason is not None:
            out.append((path, reason))
    return out


def tracked_files() -> list[str]:
    # core.quotepath=false → non-ASCII paths (e.g. cyrillic audit names) come
    # through as raw UTF-8 instead of octal-escaped, quoted strings.
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files"],
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )
    return [line for line in result.stdout.splitlines() if line]


def self_test() -> int:
    """Prove the detector flags forbidden paths and leaves legitimate ones alone."""
    must_flag = [
        "archive/2026-04-23-bcg-planning-docs/progress.md",
        "archive/smoke-runs/README.md",
        "archive",
        "audit_opus_2026-06-17.md",
        "audit_kimi_2026-04-26.md",
        "audit_кодекс_2026-04-27.md",
    ]
    must_pass = [
        "README.md",
        "docs/plans/2026-06-17-project-hardening-plan.md",
        "docs/audit_notes.md",  # nested audit_* doc is allowed (only root is internal)
        "app/backend/app/audit_log.py",  # not a markdown audit report
        "scripts/check_repo_hygiene.py",
        "archived_examples/sample.md",  # 'archive' prefix but different top-level dir
    ]
    failures: list[str] = []
    for path in must_flag:
        if classify(path) is None:
            failures.append(f"FAILED to flag forbidden path: {path!r}")
    for path in must_pass:
        reason = classify(path)
        if reason is not None:
            failures.append(f"FALSE POSITIVE on legitimate path: {path!r} -> {reason}")
    if failures:
        print("[repo-hygiene] self-test FAILED:", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(f"[repo-hygiene] self-test passed ({len(must_flag)} flagged, {len(must_pass)} clean).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Verify the detector flags forbidden paths and passes clean ones, then exit.",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    paths = tracked_files()
    violations = find_violations(paths)
    if violations:
        print(
            f"[repo-hygiene] FAILED: {len(violations)} internal-only file(s) are tracked in the public repo:",
            file=sys.stderr,
        )
        for path, reason in violations:
            print(f"  {path}  ({reason})", file=sys.stderr)
        print(
            "\nThese were untracked on 2026-06-17 and must stay out of the public tree. "
            "Remove with `git rm --cached <path>` and confirm `.gitignore` still covers them.",
            file=sys.stderr,
        )
        return 1

    print(f"[repo-hygiene] OK: {len(paths)} tracked file(s), no archive/ or root audit_*.md leaks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
