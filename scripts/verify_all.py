from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "app" / "frontend"
NPM_EXECUTABLE = "npm.cmd" if os.name == "nt" else "npm"


def format_command(command: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(command)
    return " ".join(command)


def run_step(label: str, command: list[str], cwd: Path, *, shell: bool = False) -> None:
    printable = format_command(command)
    print(f"[verify] {label}: {printable}")
    completed = subprocess.run(
        printable if shell else command,
        cwd=cwd,
        check=False,
        shell=shell,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-smoke", action="store_true", help="Skip the Playwright smoke flow.")
    parser.add_argument("--skip-build", action="store_true", help="Skip the frontend production build.")
    parser.add_argument("--with-e2e", action="store_true", help="Run the frontend Playwright E2E flow.")
    parser.add_argument("--with-docker", action="store_true", help="Run the secure docker compose verification flow.")
    args = parser.parse_args()

    if os.name == "nt":
        delegated_command = ["cmd.exe", "/d", "/c", "scripts\\verify_all.cmd"]
        if args.skip_smoke:
            delegated_command.append("--skip-smoke")
        if args.skip_build:
            delegated_command.append("--skip-build")
        if args.with_e2e:
            delegated_command.append("--with-e2e")
        if args.with_docker:
            delegated_command.append("--with-docker")
        run_step("windows verify delegation", delegated_command, ROOT_DIR)
        return 0

    run_step(
        "generated api contracts",
        [sys.executable, "scripts/generate_frontend_api_types.py", "--check"],
        ROOT_DIR,
    )
    run_step(
        "generated api docs",
        [sys.executable, "scripts/generate_api_docs.py", "--check"],
        ROOT_DIR,
    )
    run_step(
        "workspace backup roundtrip",
        [sys.executable, "scripts/verify_workspace_backup.py", "--fixture"],
        ROOT_DIR,
    )
    run_step("backend tests", [sys.executable, "-m", "pytest", "app/backend/tests", "-q"], ROOT_DIR)
    run_step(
        "backend benchmark",
        [sys.executable, "scripts/benchmark_backend.py", "--payload", "binary", "--assert-ms", "100"],
        ROOT_DIR,
    )
    run_step("frontend typecheck", [NPM_EXECUTABLE, "exec", "tsc", "--", "--noEmit", "-p", "."], FRONTEND_DIR)
    run_step("frontend unit tests", [NPM_EXECUTABLE, "run", "test:unit"], FRONTEND_DIR)

    if not args.skip_build:
        run_step("frontend build", [NPM_EXECUTABLE, "run", "build"], FRONTEND_DIR)

    if args.with_e2e:
        run_step("playwright e2e", [NPM_EXECUTABLE, "run", "test:e2e"], FRONTEND_DIR)

    if not args.skip_smoke:
        smoke_command = [sys.executable, "scripts/run_local_smoke.py"]
        if args.skip_build:
            smoke_command.append("--skip-build")
        run_step("local smoke", smoke_command, ROOT_DIR)

    if args.with_docker:
        run_step(
            "docker compose secure flow",
            [sys.executable, "scripts/verify_docker_compose.py"],
            ROOT_DIR,
        )

    print("[verify] all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
