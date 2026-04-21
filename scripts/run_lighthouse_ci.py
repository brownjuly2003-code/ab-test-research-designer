from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_HOST = "127.0.0.1"
DEFAULT_DIST_DIR = Path("app/frontend/dist")
LHCI_VERSION = "0.14.0"
NPX_EXECUTABLE = "npx.cmd" if os.name == "nt" else "npx"


def wait_for_http(url: str, timeout_seconds: float, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Backend exited before becoming ready: {process.returncode}")

        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except URLError:
            time.sleep(0.25)
            continue

        time.sleep(0.25)

    raise RuntimeError(f"Timed out waiting for {url}")


def terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return

    if os.name == "nt":
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
            process.wait(timeout=10)
            return
        except (subprocess.TimeoutExpired, ValueError):
            pass

        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        process.wait(timeout=10)
        return

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def choose_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind((BACKEND_HOST, 0))
        return int(candidate.getsockname()[1])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Lighthouse CI against the backend-served production frontend."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=4174,
        help="Port for the temporary backend-served frontend. Use 0 to choose a free port.",
    )
    parser.add_argument(
        "--dist-dir",
        default=str(DEFAULT_DIST_DIR),
        help="Path to the built frontend dist directory, relative to the repo root by default.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    port = choose_port() if args.port == 0 else args.port
    dist_dir = Path(args.dist_dir)
    if not dist_dir.is_absolute():
        dist_dir = ROOT_DIR / dist_dir
    dist_dir = dist_dir.resolve()

    if not (dist_dir / "index.html").exists():
        raise RuntimeError(f"Frontend dist is missing: {dist_dir}")

    temp_dir = Path(tempfile.mkdtemp(prefix="ab-test-lighthouse-"))
    backend_env = os.environ.copy()
    backend_env.update(
        {
            "AB_ENV": "lighthouse",
            "AB_DB_PATH": str(temp_dir / "projects.sqlite3"),
            "AB_HOST": BACKEND_HOST,
            "AB_PORT": str(port),
            "AB_SERVE_FRONTEND_DIST": "true",
            "AB_FRONTEND_DIST_PATH": str(dist_dir),
            "AB_LLM_TIMEOUT_SECONDS": "1",
            "AB_LLM_MAX_ATTEMPTS": "1",
        }
    )

    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    backend_process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.backend.app.main:app",
            "--host",
            BACKEND_HOST,
            "--port",
            str(port),
        ],
        cwd=ROOT_DIR,
        env=backend_env,
        creationflags=creationflags,
    )

    try:
        base_url = f"http://{BACKEND_HOST}:{port}/"
        wait_for_http(f"{base_url}health", timeout_seconds=30, process=backend_process)
        lhci_env = os.environ.copy()
        lhci_env["LHCI_URL"] = base_url
        completed = subprocess.run(
            [
                NPX_EXECUTABLE,
                "--yes",
                f"@lhci/cli@{LHCI_VERSION}",
                "autorun",
                f"--collect.url={base_url}",
            ],
            cwd=ROOT_DIR,
            env=lhci_env,
            check=False,
        )
        return completed.returncode
    finally:
        terminate_process(backend_process)


if __name__ == "__main__":
    raise SystemExit(main())
