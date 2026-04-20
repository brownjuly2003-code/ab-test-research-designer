from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "app" / "frontend"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"
BACKEND_HOST = "127.0.0.1"
NPM_EXECUTABLE = "npm.cmd" if os.name == "nt" else "npm"


def run_command(command: list[str], workdir: Path) -> None:
    subprocess.run(command, cwd=workdir, check=True)


def wait_for_http(url: str, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except URLError:
            time.sleep(0.25)
            continue

        time.sleep(0.25)

    raise RuntimeError(f"Timed out waiting for {url}")


def terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def choose_backend_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind((BACKEND_HOST, 0))
        return int(candidate.getsockname()[1])


def read_log_tail(log_path: Path, max_lines: int = 40) -> str:
    if not log_path.exists():
        return ""

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Run the frontend Playwright E2E flow against a temporary backend-served build."
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Assume app/frontend/dist already exists and skip rebuilding the frontend.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=180,
        help="Hard timeout for the Playwright command.",
    )
    return parser.parse_known_args()


def main() -> int:
    args, passthrough_args = parse_args()

    if not args.skip_build:
        run_command([NPM_EXECUTABLE, "run", "build"], FRONTEND_DIR)

    if not (FRONTEND_DIST_DIR / "index.html").exists():
        raise RuntimeError("Frontend dist is missing. Run `npm run build` in app/frontend first.")

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = ROOT_DIR / "archive" / "e2e-runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "projects.sqlite3"
    backend_log_path = run_dir / "backend.log"
    playwright_log_path = run_dir / "playwright.log"
    backend_port = choose_backend_port()
    base_url = f"http://{BACKEND_HOST}:{backend_port}"

    backend_env = os.environ.copy()
    backend_env.update(
        {
            "AB_ENV": "playwright",
            "AB_DB_PATH": str(db_path),
            "AB_HOST": BACKEND_HOST,
            "AB_PORT": str(backend_port),
        }
    )

    with backend_log_path.open("w", encoding="utf-8") as backend_log:
        backend_process = subprocess.Popen(
            [sys.executable, str(ROOT_DIR / "scripts" / "run_backend_for_e2e.py")],
            cwd=ROOT_DIR,
            env=backend_env,
            stdout=backend_log,
            stderr=subprocess.STDOUT,
            text=True,
        )

        try:
            wait_for_http(f"{base_url}/health", timeout_seconds=30)
            wait_for_http(base_url, timeout_seconds=30)

            playwright_env = os.environ.copy()
            playwright_env["AB_E2E_BASE_URL"] = base_url

            command = [
                NPM_EXECUTABLE,
                "exec",
                "--",
                "playwright",
                "test",
                "-c",
                "playwright.config.ts",
                *passthrough_args,
            ]

            with playwright_log_path.open("w", encoding="utf-8") as playwright_log:
                playwright_process = subprocess.Popen(
                    command,
                    cwd=FRONTEND_DIR,
                    env=playwright_env,
                    stdout=playwright_log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

                try:
                    return_code = playwright_process.wait(timeout=args.timeout_seconds)
                except subprocess.TimeoutExpired as error:
                    terminate_process(playwright_process)
                    raise RuntimeError(
                        f"Playwright timed out after {args.timeout_seconds} seconds."
                    ) from error
        finally:
            terminate_process(backend_process)

    if return_code != 0:
        backend_tail = read_log_tail(backend_log_path)
        playwright_tail = read_log_tail(playwright_log_path)
        if backend_tail:
            print(backend_tail, file=sys.stderr)
        if playwright_tail:
            print(playwright_tail, file=sys.stderr)
        print(f"Backend log: {backend_log_path}", file=sys.stderr)
        print(f"Playwright log: {playwright_log_path}", file=sys.stderr)
        raise SystemExit(return_code)

    print(f"Playwright E2E passed. Logs: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
