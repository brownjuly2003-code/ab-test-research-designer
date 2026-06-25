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
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REPO_ID = "liovina/ab-test-research-designer"

# Identical to docs/DEPLOY.md — keeps the upload to the proven source set and
# strips build artefacts, caches, local DBs and internal demo assets.
IGNORE_PATTERNS = [
    ".git/**",
    "**/__pycache__/**",
    "archive/**",
    "docs/demo/*.png",
    "*.sqlite3*",
    "**/node_modules/**",
]


def upload_snapshot(repo_id: str, token: str, commit_message: str) -> str:
    """Upload the working tree to the Space; return the resulting commit URL/oid."""
    from huggingface_hub import upload_folder

    result = upload_folder(
        folder_path=str(ROOT_DIR),
        repo_id=repo_id,
        repo_type="space",
        token=token,
        ignore_patterns=IGNORE_PATTERNS,
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
    args = parser.parse_args()

    if args.dry_run:
        print(f"[deploy] DRY RUN — would upload {ROOT_DIR} -> space {args.repo_id}")
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
