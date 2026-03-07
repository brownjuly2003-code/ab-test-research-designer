from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "app" / "frontend"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8010
BACKEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"


def run_command(command: list[str], workdir: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=workdir, env=env, check=True)


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


def start_backend_process(temp_db_path: Path) -> subprocess.Popen[str]:
    backend_env = os.environ.copy()
    backend_env.update(
        {
            "AB_ENV": "smoke",
            "AB_DB_PATH": str(temp_db_path),
            "AB_HOST": BACKEND_HOST,
            "AB_PORT": str(BACKEND_PORT),
            "AB_SERVE_FRONTEND_DIST": "true",
            "AB_FRONTEND_DIST_PATH": str(FRONTEND_DIST_DIR),
            "AB_CORS_ORIGINS": "http://127.0.0.1:5173,http://localhost:5173",
        }
    )

    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.backend.app.main:app",
            "--host",
            BACKEND_HOST,
            "--port",
            str(BACKEND_PORT),
        ],
        cwd=ROOT_DIR,
        env=backend_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def read_process_output(process: subprocess.Popen[str]) -> str:
    try:
        stdout, _ = process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        return ""

    return stdout or ""


def run_browser_smoke(download_dir: Path, screenshot_path: Path) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            page.goto(BACKEND_URL, wait_until="networkidle")
            page.get_by_role("heading", name="AB Test Research Designer").wait_for(timeout=15000)
            page.get_by_text("API online").wait_for(timeout=15000)

            page.get_by_role("button", name="Save project").click()
            page.get_by_text("Project saved locally with id", exact=False).wait_for(timeout=15000)
            page.get_by_role("button", name="Checkout redesign", exact=True).wait_for(timeout=15000)

            project_name_input = page.locator("#project-project_name")
            project_name_input.fill("Smoke restored draft")
            page.reload(wait_until="networkidle")

            page.get_by_text("Restored unsaved browser draft.").wait_for(timeout=15000)
            reloaded_value = page.locator("#project-project_name").input_value()
            if reloaded_value != "Smoke restored draft":
                raise RuntimeError(
                    f"Expected browser draft restore to keep project name, got: {reloaded_value!r}"
                )

            for _ in range(5):
                page.get_by_role("button", name="Next").click()

            page.get_by_text("Review inputs").wait_for(timeout=15000)
            page.get_by_role("button", name="Run analysis").click()

            page.get_by_text("Analysis completed.", exact=False).wait_for(timeout=30000)
            page.get_by_text("Deterministic experiment design").wait_for(timeout=30000)
            page.get_by_text("Calculation summary").wait_for(timeout=30000)

            with page.expect_download(timeout=15000) as download_info:
                page.get_by_role("button", name="Export Markdown").click()

            markdown_download = download_info.value
            markdown_path = download_dir / "experiment-report.md"
            markdown_download.save_as(markdown_path)
            markdown_text = markdown_path.read_text(encoding="utf-8")
            if "# Experiment Report" not in markdown_text:
                raise RuntimeError("Smoke export did not produce the expected markdown report header.")
        except (AssertionError, RuntimeError, PlaywrightTimeoutError):
            page.screenshot(path=str(screenshot_path), full_page=True)
            raise
        finally:
            context.close()
            browser.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local browser smoke test against the backend-served frontend.")
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Assume app/frontend/dist already exists and skip rebuilding the frontend.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.skip_build:
        run_command(["npm.cmd", "run", "build"], FRONTEND_DIR)

    if not (FRONTEND_DIST_DIR / "index.html").exists():
        raise RuntimeError("Frontend dist is missing. Run `npm.cmd run build` in app/frontend first.")

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    temp_dir = ROOT_DIR / "archive" / "smoke-runs" / run_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_db_path = temp_dir / "projects.sqlite3"
    screenshot_path = temp_dir / "smoke-failure.png"
    download_dir = temp_dir / "downloads"
    download_dir.mkdir(parents=True, exist_ok=True)

    backend_process = start_backend_process(temp_db_path)

    try:
        wait_for_http(f"{BACKEND_URL}/health", timeout_seconds=30)
        wait_for_http(BACKEND_URL, timeout_seconds=30)
        run_browser_smoke(download_dir=download_dir, screenshot_path=screenshot_path)
    except Exception:
        terminate_process(backend_process)
        output = read_process_output(backend_process)
        if output:
            print(output, file=sys.stderr)
        if screenshot_path.exists():
            print(f"Smoke screenshot: {screenshot_path}", file=sys.stderr)
        raise
    finally:
        terminate_process(backend_process)

    print(f"Smoke test passed. Downloaded report: {download_dir / 'experiment-report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
