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


def run_step(
    label: str,
    command: list[str],
    cwd: Path,
    *,
    shell: bool = False,
    env: dict[str, str] | None = None,
) -> None:
    printable = format_command(command)
    print(f"[verify] {label}: {printable}")
    completed = subprocess.run(
        printable if shell else command,
        cwd=cwd,
        check=False,
        shell=shell,
        env=env,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-smoke", action="store_true", help="Skip the Playwright smoke flow.")
    parser.add_argument("--skip-build", action="store_true", help="Skip the frontend production build.")
    parser.add_argument("--with-e2e", action="store_true", help="Run the frontend Playwright E2E flow.")
    docker_group = parser.add_mutually_exclusive_group()
    docker_group.add_argument("--with-docker", action="store_true", help="Run the secure docker compose verification flow.")
    docker_group.add_argument(
        "--with-docker-preserve",
        action="store_true",
        help="Run the secure docker compose verification flow without tearing the stack down.",
    )
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
        if args.with_docker_preserve:
            delegated_command.append("--with-docker-preserve")
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
    unsigned_backup_env = os.environ.copy()
    unsigned_backup_env.pop("AB_WORKSPACE_SIGNING_KEY", None)
    run_step(
        "workspace backup roundtrip (checksum)",
        [sys.executable, "scripts/verify_workspace_backup.py", "--fixture"],
        ROOT_DIR,
        env=unsigned_backup_env,
    )
    signed_backup_env = os.environ.copy()
    signed_backup_env["AB_WORKSPACE_SIGNING_KEY"] = "verify-workspace-signing-key"
    run_step(
        "workspace backup roundtrip (signed)",
        [sys.executable, "scripts/verify_workspace_backup.py", "--fixture"],
        ROOT_DIR,
        env=signed_backup_env,
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
        run_step(
            "playwright e2e",
            [sys.executable, "scripts/run_frontend_e2e.py", "--skip-build"],
            ROOT_DIR,
        )

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
    elif args.with_docker_preserve:
        run_step(
            "docker compose secure flow (preserve)",
            [sys.executable, "scripts/verify_docker_compose.py", "--preserve"],
            ROOT_DIR,
        )

    print("[verify] all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
