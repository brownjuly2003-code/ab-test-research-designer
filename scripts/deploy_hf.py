"""Deploy the repository snapshot to the Hugging Face Space and smoke /health.

Mirrors the manual recipe documented in docs/DEPLOY.md so the CI workflow and a
local operator run identically. The Space is a Docker SDK Space that builds the
frontend itself (see Dockerfile), so this only uploads the source tree — HF
rebuilds the container. A write-scoped token must be provided via the HF_TOKEN
environment variable (never passed on the command line).

Usage (CI / local):
    HF_TOKEN=*** python scripts/deploy_hf.py \
        --health-url https://liovina-ab-test-research-designer.hf.space/health \
        --health-timeout 600
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from fnmatch import fnmatch
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REPO_ID = "liovina/ab-test-research-designer"

# Identical to docs/DEPLOY.md — keeps the upload to the proven source set and
# strips build artefacts, caches, local DBs and internal demo assets.
#
# These are the second line of defence. The first is `tracked_files()`: the Space is
# public, so only files git tracks are ever uploaded. Both are needed — a pattern here
# also protects a file that someone tracks by mistake.
IGNORE_PATTERNS = [
    ".git/**",
    "**/__pycache__/**",
    "archive/**",
    "docs/demo/*.png",
    "*.sqlite3*",
    "**/node_modules/**",
    # Internal notes that must never reach a public Space, mirroring the classes
    # check_repo_hygiene.py keeps out of the index.
    "audit_*.md",
    "_*.md",
    ".claude/**",
    ".cx_polls/**",
]

# Managed by Hugging Face, not by this repo: never prune it when mirroring.
PRESERVE_ON_SPACE = {".gitattributes"}


def tracked_files() -> list[str]:
    """Return every path git tracks, relative to the repo root, as posix strings.

    `upload_folder` walks the *working tree*, not the index. Untracked files therefore
    ship too — internal audit reports, session handoffs, scratch token files — straight
    into a public Space. Restricting the upload to tracked paths makes that structurally
    impossible, and it reproduces exactly what a clean CI checkout would have uploaded.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(
            f"[deploy] cannot list tracked files ({error}). Refusing to upload the working "
            "tree unfiltered: it may hold internal notes."
        ) from error

    paths = [line for line in result.stdout.split("\0") if line]
    if not paths:
        raise SystemExit("[deploy] git reported no tracked files; refusing to upload.")
    return paths


def is_ignored(path: str) -> bool:
    """True when ``path`` matches IGNORE_PATTERNS, using huggingface_hub's own semantics.

    ``huggingface_hub`` filters with :func:`fnmatch.fnmatch`, where ``*`` also crosses ``/``.
    A pattern therefore matches from the start of the repo-relative posix path, which is why
    ``audit_*.md`` catches the root reports and leaves ``docs/plans/…-audit-report.md`` alone.
    """
    return any(fnmatch(path, pattern) for pattern in IGNORE_PATTERNS)


def self_test() -> int:
    """Prove the publish filter drops internal notes and keeps the files the Space needs."""
    must_exclude = [
        "audit_07_07_26.md",
        "audit_opus_2026-06-17.md",
        "_NEXT_SESSION.md",
        ".claude/settings.local.json",
        ".cx_polls/poll.json",
        "archive/smoke-runs/20260709-104049/downloads/experiment-report.md",
        "app/backend/data/app.sqlite3",
        "docs/demo/wizard-overview.png",
        "app/frontend/node_modules/react/index.js",
        ".git/config",
    ]
    must_publish = [
        "README.md",
        "Dockerfile",
        "app/backend/requirements.txt",
        "app/backend/app/main.py",
        "app/frontend/src/components/SidebarPanel.tsx",
        "docs/DEPLOY.md",
        # Audit *reports under docs/* are part of the published documentation set and
        # are already tracked in the public repo; only the root-level notes are internal.
        "docs/plans/2026-04-21-a11y-audit-report.md",
    ]

    failures: list[str] = []
    for path in must_exclude:
        if not is_ignored(path):
            failures.append(f"should be excluded but is not: {path}")
    for path in must_publish:
        if is_ignored(path):
            failures.append(f"should be published but is excluded: {path}")

    if failures:
        print("[deploy] self-test FAILED:", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(
        f"[deploy] self-test passed ({len(must_exclude)} excluded, {len(must_publish)} published). "
        "Untracked files are dropped separately by the git allowlist."
    )
    return 0


def stale_space_paths(repo_id: str, token: str, publishable: set[str]) -> list[str]:
    """Files the Space still serves that this upload no longer ships.

    ``upload_folder`` only adds and updates. Without an explicit delete list the Space keeps
    every file any past upload ever put there: decommissioned modules (a pre-split
    ``repository.py`` sitting next to the ``repository/`` package that replaced it), local
    caches, and internal notes from a working-tree deploy. The Space must mirror the repo.
    """
    from huggingface_hub import HfApi

    existing = set(HfApi(token=token).list_repo_files(repo_id, repo_type="space"))
    return sorted(existing - publishable - PRESERVE_ON_SPACE)


def current_git_sha() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = completed.stdout.strip()
    return sha or None


def stamp_build_sha(repo_id: str, token: str) -> None:
    """Expose the deployed commit to the Space via the AB_BUILD_SHA variable.

    The Space builds the Dockerfile itself and passes no build args, and the image
    carries no .git, so without this stamp /health reports git_sha="unknown"
    (audit F-07). Stamped before the upload: the variable change restarts the old
    container once, then the upload's rebuild wins. Failure to stamp is a warning,
    not a failed deploy — the fallback stays an honest "unknown".
    """
    sha = current_git_sha()
    if not sha:
        print("[deploy] WARNING: could not resolve git sha; AB_BUILD_SHA not stamped", file=sys.stderr)
        return
    from huggingface_hub import HfApi

    try:
        HfApi(token=token).add_space_variable(
            repo_id,
            "AB_BUILD_SHA",
            sha,
            description="Deployed git commit, stamped by scripts/deploy_hf.py",
        )
    except Exception as exc:  # noqa: BLE001 - stamping must never block a deploy
        print(f"[deploy] WARNING: failed to stamp AB_BUILD_SHA: {exc}", file=sys.stderr)
        return
    print(f"[deploy] stamped AB_BUILD_SHA={sha}")


def upload_snapshot(repo_id: str, token: str, commit_message: str) -> str:
    """Mirror the git-tracked source tree onto the Space; return the commit URL/oid."""
    from huggingface_hub import upload_folder

    publishable = [path for path in tracked_files() if not is_ignored(path)]
    print(f"[deploy] publishing {len(publishable)} git-tracked file(s); untracked paths are skipped")

    stale = stale_space_paths(repo_id, token, set(publishable))
    if stale:
        preview = ", ".join(stale[:3])
        print(f"[deploy] pruning {len(stale)} stale file(s) from the Space (e.g. {preview})")

    result = upload_folder(
        folder_path=str(ROOT_DIR),
        repo_id=repo_id,
        repo_type="space",
        token=token,
        allow_patterns=publishable,
        ignore_patterns=IGNORE_PATTERNS,
        delete_patterns=stale or None,
        commit_message=commit_message,
    )
    return str(result)


def wait_healthy(url: str, timeout_seconds: int, interval_seconds: int = 15) -> bool:
    """Poll ``url`` until it returns HTTP 200 or the timeout elapses.

    HF keeps the previous container live during a rebuild, so a 200 confirms the
    Space is reachable and serving; the new build going live end-to-end is
    verified separately by the Playwright live check (Phase 5).
    """
    deadline = time.monotonic() + timeout_seconds
    last_error = "no attempt made"
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                if response.status == 200:
                    print(f"[deploy] health OK after {attempt} attempt(s): {url}")
                    return True
                last_error = f"HTTP {response.status}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
        print(f"[deploy] health not ready (attempt {attempt}): {last_error}")
        time.sleep(interval_seconds)
    print(f"[deploy] health check FAILED after {timeout_seconds}s: {last_error}", file=sys.stderr)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-id", default=os.environ.get("AB_HF_SPACE_REPO", DEFAULT_REPO_ID))
    parser.add_argument("--health-url", default=None, help="If set, poll this URL for HTTP 200 after upload.")
    parser.add_argument("--health-timeout", type=int, default=600, help="Seconds to wait for /health.")
    parser.add_argument("--commit-message", default="Deploy from CI", help="Space commit message.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and print the plan without uploading (no token required).",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Verify the publish filter excludes internal notes and keeps Space sources, then exit.",
    )
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if args.dry_run:
        published = [path for path in tracked_files() if not is_ignored(path)]
        print(f"[deploy] DRY RUN — would upload {ROOT_DIR} -> space {args.repo_id}")
        print(f"[deploy] {len(published)} git-tracked file(s) pass the filter")
        print(f"[deploy] ignore_patterns={IGNORE_PATTERNS}")
        if args.health_url:
            print(f"[deploy] would smoke health: {args.health_url} (timeout {args.health_timeout}s)")
        return 0

    token = os.environ.get("HF_TOKEN") or os.environ.get("AB_HF_TOKEN")
    if not token:
        print(
            "[deploy] ERROR: HF_TOKEN is not set. In CI add a repository secret "
            "(gh secret set HF_TOKEN); locally export HF_TOKEN before running.",
            file=sys.stderr,
        )
        return 2

    stamp_build_sha(args.repo_id, token)

    print(f"[deploy] uploading {ROOT_DIR} -> space {args.repo_id}")
    commit = upload_snapshot(args.repo_id, token, args.commit_message)
    print(f"[deploy] upload committed: {commit}")

    if args.health_url:
        if not wait_healthy(args.health_url, args.health_timeout):
            return 1

    print("[deploy] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
