from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "app" / "frontend"
NPM_EXECUTABLE = "npm.cmd" if os.name == "nt" else "npm"
POWERSHELL_EXECUTABLE = "powershell.exe"


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


def run_windows_powershell_step(label: str, command_text: str, cwd: Path) -> None:
    run_step(
        label,
        [POWERSHELL_EXECUTABLE, "-NoProfile", "-Command", command_text],
        cwd,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-smoke", action="store_true", help="Skip the Playwright smoke flow.")
    parser.add_argument("--skip-build", action="store_true", help="Skip the frontend production build.")
    args = parser.parse_args()

    if os.name == "nt":
        print("Use `cmd /c scripts\\verify_all.cmd` on Windows.")
        return 2

    run_step(
        "generated api contracts",
        [sys.executable, "scripts/generate_frontend_api_types.py", "--check"],
        ROOT_DIR,
    )
    run_step("backend tests", [sys.executable, "-m", "pytest", "app/backend/tests", "-q"], ROOT_DIR)
    if os.name == "nt":
        run_windows_powershell_step(
            "frontend typecheck",
            "npm.cmd exec tsc -- --noEmit -p .",
            FRONTEND_DIR,
        )
        run_windows_powershell_step(
            "frontend unit tests",
            "npm.cmd run test:unit",
            FRONTEND_DIR,
        )
    else:
        run_step("frontend typecheck", [NPM_EXECUTABLE, "exec", "tsc", "--", "--noEmit", "-p", "."], FRONTEND_DIR)
        run_step("frontend unit tests", [NPM_EXECUTABLE, "run", "test:unit"], FRONTEND_DIR)

    if not args.skip_build:
        if os.name == "nt":
            run_windows_powershell_step("frontend build", "npm.cmd run build", FRONTEND_DIR)
        else:
            run_step("frontend build", [NPM_EXECUTABLE, "run", "build"], FRONTEND_DIR)

    if not args.skip_smoke:
        smoke_command = [sys.executable, "scripts/run_local_smoke.py"]
        if args.skip_build:
            smoke_command.append("--skip-build")
        run_step("local smoke", smoke_command, ROOT_DIR)

    print("[verify] all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
