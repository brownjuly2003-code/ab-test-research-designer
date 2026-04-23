from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import socket
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
DEMO_DIR = ROOT_DIR / "docs" / "demo"
BACKEND_HOST = "127.0.0.1"
BROWSER_DRAFT_STORAGE_KEY = "ab-test-research-designer:draft:v1"
NPM_EXECUTABLE = "npm.cmd" if os.name == "nt" else "npm"


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


def choose_backend_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind((BACKEND_HOST, 0))
        return int(candidate.getsockname()[1])


def start_backend_process(
    temp_db_path: Path,
    backend_port: int,
    backend_env: dict[str, str] | None = None,
) -> subprocess.Popen[str]:
    process_env = os.environ.copy() if backend_env is None else backend_env.copy()
    process_env.update(
        {
            "AB_ENV": "smoke",
            "AB_DB_PATH": str(temp_db_path),
            "AB_HOST": BACKEND_HOST,
            "AB_PORT": str(backend_port),
            "AB_SERVE_FRONTEND_DIST": "true",
            "AB_FRONTEND_DIST_PATH": str(FRONTEND_DIST_DIR),
            "AB_CORS_ORIGINS": "http://127.0.0.1:5173,http://localhost:5173",
            "AB_LLM_TIMEOUT_SECONDS": "1",
            "AB_LLM_MAX_ATTEMPTS": "1",
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
            str(backend_port),
        ],
        cwd=ROOT_DIR,
        env=process_env,
    )


def append_smoke_log(log_path: Path, message: str) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def run_browser_smoke(
    download_dir: Path,
    screenshot_path: Path,
    failure_dom_path: Path,
    *,
    backend_url: str,
    api_token: str,
    admin_token: str,
    log_path: Path,
) -> None:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    archive_screenshots_dir = download_dir.parent / "screenshots"
    archive_screenshots_dir.mkdir(parents=True, exist_ok=True)

    def write_screenshot(page, target: Path, *, full_page: bool = False, scroll_to_top: bool = True) -> None:
        if scroll_to_top:
            page.evaluate("window.scrollTo(0, 0)")
        page.screenshot(
            path=str(target),
            full_page=full_page,
            animations="disabled",
            timeout=30000,
        )

    def capture_success_screenshot(
        page,
        archive_name: str,
        stable_name: str,
        *,
        full_page: bool = False,
        scroll_to_top: bool = True,
    ) -> None:
        page.wait_for_timeout(400)
        archive_target = archive_screenshots_dir / archive_name
        stable_target = DEMO_DIR / stable_name
        write_screenshot(page, archive_target, full_page=full_page, scroll_to_top=scroll_to_top)
        stable_target.write_bytes(archive_target.read_bytes())

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1440, "height": 1400},
        )
        page = context.new_page()
        write_headers = {"Authorization": f"Bearer {api_token}"} if api_token else {}
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        json_headers = {"Content-Type": "application/json", **write_headers}
        admin_json_headers = {"Content-Type": "application/json", **admin_headers}

        try:
            if api_token or admin_token:
                page.add_init_script(
                    script=(
                        "const apiToken = "
                        f"{json.dumps(api_token)};"
                        "const adminToken = "
                        f"{json.dumps(admin_token)};"
                        "if (apiToken) { window.sessionStorage.setItem('ab-test-research-designer:api-token:v1', apiToken); }"
                        "if (adminToken) { window.sessionStorage.setItem('ab-test-research-designer:admin-token:v1', adminToken); }"
                    )
                )

            append_smoke_log(log_path, "preparing seeded comparison snapshots")
            print("[smoke] preparing seeded comparison snapshots", flush=True)
            projects_response = context.request.get(
                f"{backend_url}/api/v1/projects?status=all&limit=200",
                headers=write_headers,
            )
            if not projects_response.ok:
                raise RuntimeError(
                    "Smoke could not list seeded projects. "
                    f"status={projects_response.status} body={projects_response.text()!r}"
                )
            seeded_projects = [
                project
                for project in projects_response.json().get("projects", [])
                if str(project.get("project_name", "")).startswith("Demo - ")
            ]
            if len(seeded_projects) < 2:
                raise RuntimeError(
                    "Smoke expected at least two seeded demo projects for comparison screenshots."
                )

            for seeded_project in seeded_projects[:2]:
                project_id = str(seeded_project["id"])
                detail_response = context.request.get(
                    f"{backend_url}/api/v1/projects/{project_id}",
                    headers=write_headers,
                )
                if not detail_response.ok:
                    raise RuntimeError(
                        "Smoke could not load a seeded project. "
                        f"project_id={project_id!r} status={detail_response.status} body={detail_response.text()!r}"
                    )
                project_record = detail_response.json()
                project_payload = project_record.get("payload")
                if not isinstance(project_payload, dict):
                    raise RuntimeError(f"Seeded project {project_id!r} did not expose a payload.")

                metric_type = project_payload.get("metrics", {}).get("metric_type")
                if metric_type == "continuous":
                    results_request = {
                        "metric_type": "continuous",
                        "continuous": {
                            "control_mean": 120.0,
                            "control_std": 18.5,
                            "control_n": 4200,
                            "treatment_mean": 126.3,
                            "treatment_std": 19.1,
                            "treatment_n": 4150,
                            "alpha": 0.05,
                        },
                    }
                else:
                    results_request = {
                        "metric_type": "binary",
                        "binary": {
                            "control_conversions": 356,
                            "control_users": 8200,
                            "treatment_conversions": 401,
                            "treatment_users": 8150,
                            "alpha": 0.05,
                        },
                    }

                observed_results_response = context.request.post(
                    f"{backend_url}/api/v1/results",
                    data=json.dumps(results_request),
                    headers=json_headers,
                )
                if not observed_results_response.ok:
                    raise RuntimeError(
                        "Smoke could not calculate observed results for a seeded project. "
                        f"project_id={project_id!r} status={observed_results_response.status} "
                        f"body={observed_results_response.text()!r}"
                    )

                additional_context = project_payload.setdefault("additional_context", {})
                additional_context["observed_results"] = {
                    "request": results_request,
                    "analysis": observed_results_response.json(),
                    "saved_at": datetime.now(UTC).isoformat(timespec="seconds"),
                }

                update_project_response = context.request.put(
                    f"{backend_url}/api/v1/projects/{project_id}",
                    data=json.dumps(project_payload),
                    headers=json_headers,
                )
                if not update_project_response.ok:
                    raise RuntimeError(
                        "Smoke could not persist observed results on a seeded project. "
                        f"project_id={project_id!r} status={update_project_response.status} "
                        f"body={update_project_response.text()!r}"
                    )

                analysis_response = context.request.post(
                    f"{backend_url}/api/v1/analyze",
                    data=json.dumps(project_payload),
                    headers=json_headers,
                )
                if not analysis_response.ok:
                    raise RuntimeError(
                        "Smoke could not analyze a seeded project. "
                        f"project_id={project_id!r} status={analysis_response.status} body={analysis_response.text()!r}"
                    )

                record_analysis_response = context.request.post(
                    f"{backend_url}/api/v1/projects/{project_id}/analysis",
                    data=analysis_response.text(),
                    headers=json_headers,
                )
                if not record_analysis_response.ok:
                    raise RuntimeError(
                        "Smoke could not record an analysis snapshot for a seeded project. "
                        f"project_id={project_id!r} status={record_analysis_response.status} "
                        f"body={record_analysis_response.text()!r}"
                    )

            append_smoke_log(log_path, "creating demo webhook subscription")
            print("[smoke] creating demo webhook subscription", flush=True)
            webhook_response = context.request.post(
                f"{backend_url}/api/v1/webhooks",
                data=json.dumps(
                    {
                        "name": "Slack alerts",
                        "target_url": "https://hooks.slack.com/demo/placeholder",
                        "secret": "smoke-webhook-secret",
                        "format": "slack",
                        "event_filter": ["analysis_run_created"],
                        "scope": "global",
                    }
                ),
                headers=admin_json_headers,
            )
            if not webhook_response.ok:
                raise RuntimeError(
                    "Smoke could not create a demo webhook subscription. "
                    f"status={webhook_response.status} body={webhook_response.text()!r}"
                )

            append_smoke_log(log_path, f"opening {backend_url}")
            print(f"[smoke] opening {backend_url}", flush=True)
            page.goto(backend_url, wait_until="networkidle")
            page.get_by_role("heading", name="AB Test Research Designer").wait_for(timeout=15000)
            page.get_by_text("Plan your A/B experiment", exact=False).wait_for(timeout=15000)
            page.get_by_role("button", name="System", exact=True).click()
            page.get_by_text("API online", exact=False).wait_for(timeout=15000)
            page.get_by_role("button", name="Projects", exact=True).click()

            append_smoke_log(log_path, "loading onboarding example")
            print("[smoke] loading onboarding example", flush=True)
            page.get_by_role("button", name="Load example", exact=True).click()
            page.get_by_text(
                "Example loaded - click Run analysis to see results",
                exact=False,
            ).first.wait_for(timeout=15000)

            project_name_input = page.locator("#project-project_name")
            if project_name_input.input_value() != "Checkout redesign":
                raise RuntimeError("Smoke import did not populate the demo project name.")

            project_description_input = page.locator("#project-project_description")
            if "simplified checkout flow" not in project_description_input.input_value():
                raise RuntimeError("Smoke import did not populate the demo project description.")

            language_switcher_buttons = page.locator('[role="group"]').nth(0).locator("button.theme-toggle-button")
            if language_switcher_buttons.count() != 4:
                raise RuntimeError("Smoke expected the 4-button language switcher to remain visible.")

            append_smoke_log(log_path, "verifying browser draft persistence")
            print("[smoke] verifying browser draft persistence", flush=True)
            project_name_input.fill("Smoke draft persistence check")
            page.wait_for_function(
                """
                ([storageKey, expectedValue]) => {
                    const storedDraft = window.localStorage.getItem(storageKey);
                    return typeof storedDraft === "string" && storedDraft.includes(expectedValue);
                }
                """,
                arg=[BROWSER_DRAFT_STORAGE_KEY, "Smoke draft persistence check"],
                timeout=15000,
            )
            project_name_input.fill("Checkout redesign")
            page.wait_for_function(
                """
                ([storageKey, expectedValue]) => {
                    const storedDraft = window.localStorage.getItem(storageKey);
                    return typeof storedDraft === "string" && storedDraft.includes(expectedValue);
                }
                """,
                arg=[BROWSER_DRAFT_STORAGE_KEY, "Checkout redesign"],
                timeout=15000,
            )

            append_smoke_log(log_path, "capturing wizard overview")
            print("[smoke] capturing wizard overview", flush=True)
            capture_success_screenshot(page, "wizard-overview.png", "wizard-overview.png")

            for _ in range(5):
                page.get_by_role("button", name="Next").click()

            page.get_by_text("Review inputs").wait_for(timeout=15000)
            append_smoke_log(log_path, "capturing review step")
            print("[smoke] capturing review step", flush=True)
            capture_success_screenshot(page, "review-step.png", "review-step.png")
            append_smoke_log(log_path, "running analysis")
            print("[smoke] running analysis", flush=True)
            page.get_by_role("button", name="Run analysis").click()

            page.wait_for_timeout(750)
            if page.get_by_text("Fix these fields before saving or running analysis:", exact=False).is_visible():
                status_text = page.locator(".status").all_inner_texts()
                error_text = page.locator(".error").all_inner_texts()
                raise RuntimeError(
                    "Smoke analysis was blocked by validation. "
                    f"status={status_text!r} error={error_text!r}"
                )

            page.get_by_text("Analysis completed.", exact=False).first.wait_for(timeout=30000)
            page.get_by_text("Deterministic experiment design").wait_for(timeout=30000)
            page.get_by_text("Calculation summary").wait_for(timeout=30000)
            append_smoke_log(log_path, "capturing results dashboard")
            print("[smoke] capturing results dashboard", flush=True)
            capture_success_screenshot(
                page,
                "results-dashboard.png",
                "results-dashboard.png",
                full_page=True,
            )

            append_smoke_log(log_path, "exporting markdown")
            print("[smoke] exporting markdown", flush=True)
            page.get_by_role("button", name="Export", exact=True).click()
            page.locator("#report-export-menu").wait_for(timeout=15000)
            with page.expect_response(
                lambda response: response.request.method == "POST" and response.url.endswith("/api/v1/export/markdown"),
                timeout=15000,
            ) as response_info:
                page.get_by_role("button", name="Export Markdown", exact=True).click()

            markdown_path = download_dir / "experiment-report.md"
            markdown_payload = json.loads(response_info.value.text())
            markdown_path.write_text(markdown_payload["content"], encoding="utf-8")
            markdown_text = markdown_path.read_text(encoding="utf-8")
            if "# Experiment Report" not in markdown_text:
                raise RuntimeError("Smoke export did not produce the expected markdown report header.")
            page.get_by_text("Exported report as MD.", exact=False).first.wait_for(timeout=15000)

            append_smoke_log(log_path, "exporting html")
            print("[smoke] exporting html", flush=True)
            page.get_by_role("button", name="Export", exact=True).click()
            page.locator("#report-export-menu").wait_for(timeout=15000)
            with page.expect_response(
                lambda response: response.request.method == "POST" and response.url.endswith("/api/v1/export/html"),
                timeout=15000,
            ) as response_info:
                page.get_by_role("button", name="Export HTML", exact=True).click()

            html_path = download_dir / "experiment-report.html"
            html_payload = json.loads(response_info.value.text())
            html_path.write_text(html_payload["content"], encoding="utf-8")
            html_text = html_path.read_text(encoding="utf-8")
            if "<!doctype html>" not in html_text.lower():
                raise RuntimeError("Smoke export did not produce the expected html report.")
            page.get_by_text("Exported report as HTML.", exact=False).first.wait_for(timeout=15000)

            append_smoke_log(log_path, "opening comparison dashboard")
            print("[smoke] opening comparison dashboard", flush=True)
            page.get_by_role("button", name="Projects", exact=True).click()
            compare_checkboxes = page.locator('[role="option"] input[type="checkbox"]')
            if compare_checkboxes.count() < 2:
                raise RuntimeError("Smoke expected at least two comparison-ready project checkboxes.")
            compare_checkboxes.nth(0).check()
            compare_checkboxes.nth(1).check()
            page.locator("#compare-selected-projects-button").click()
            comparison_toggle = page.locator("button").filter(has_text="Comparison").first
            if comparison_toggle.get_attribute("aria-expanded") != "true":
                comparison_toggle.click()
            page.locator('[data-testid="comparison-dashboard"]').wait_for(state="visible", timeout=15000)
            page.locator('[data-testid="forest-plot-row"]').first.wait_for(state="visible", timeout=15000)
            append_smoke_log(log_path, "capturing comparison dashboard")
            print("[smoke] capturing comparison dashboard", flush=True)
            capture_success_screenshot(
                page,
                "comparison-dashboard.png",
                "comparison-dashboard.png",
                full_page=True,
            )

            append_smoke_log(log_path, "opening webhook manager")
            print("[smoke] opening webhook manager", flush=True)
            page.get_by_role("button", name="API keys", exact=True).click()
            page.get_by_test_id("webhook-manager").wait_for(timeout=15000)
            webhook_heading = page.get_by_role("heading", name="Webhooks", exact=True)
            webhook_heading.scroll_into_view_if_needed()
            page.get_by_test_id("webhook-subscription-row").first.wait_for(timeout=15000)
            append_smoke_log(log_path, "capturing webhook manager")
            print("[smoke] capturing webhook manager", flush=True)
            capture_success_screenshot(
                page,
                "webhook-manager.png",
                "webhook-manager.png",
                scroll_to_top=False,
            )

            append_smoke_log(log_path, "smoke flow completed")
        except (AssertionError, RuntimeError, PlaywrightTimeoutError) as smoke_error:
            append_smoke_log(log_path, f"smoke error: {smoke_error!r}")
            append_smoke_log(log_path, "capturing failure artifacts")
            try:
                write_screenshot(page, screenshot_path)
            except Exception as artifact_error:  # pragma: no cover - best effort diagnostics only
                append_smoke_log(log_path, f"failure screenshot skipped: {artifact_error}")
            try:
                failure_dom_path.write_text(page.content(), encoding="utf-8")
            except Exception as artifact_error:  # pragma: no cover - best effort diagnostics only
                append_smoke_log(log_path, f"failure dom dump skipped: {artifact_error}")
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
        run_command([NPM_EXECUTABLE, "run", "build"], FRONTEND_DIR)

    if not (FRONTEND_DIST_DIR / "index.html").exists():
        raise RuntimeError("Frontend dist is missing. Run `npm run build` in app/frontend first.")

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    temp_dir = ROOT_DIR / "archive" / "smoke-runs" / run_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_db_path = temp_dir / "projects.sqlite3"
    screenshot_path = temp_dir / "smoke-failure.png"
    failure_dom_path = temp_dir / "smoke-failure.html"
    log_path = temp_dir / "smoke.log"
    download_dir = temp_dir / "downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    backend_port = choose_backend_port()
    backend_url = f"http://{BACKEND_HOST}:{backend_port}"
    backend_env = os.environ.copy()
    smoke_write_token = (backend_env.get("AB_API_TOKEN") or "").strip()
    if (backend_env.get("AB_READONLY_API_TOKEN") or "").strip() and not smoke_write_token:
        smoke_write_token = "smoke-write-token"
        backend_env["AB_API_TOKEN"] = smoke_write_token
    smoke_admin_token = (
        (backend_env.get("AB_ADMIN_TOKEN") or "").strip()
        or smoke_write_token
        or "smoke-admin-token"
    )
    backend_env["AB_ADMIN_TOKEN"] = smoke_admin_token
    append_smoke_log(log_path, f"prepared run in {temp_dir}")
    append_smoke_log(log_path, f"using backend {backend_url}")

    backend_process = start_backend_process(temp_db_path, backend_port, backend_env)

    try:
        wait_for_http(f"{backend_url}/health", timeout_seconds=30)
        wait_for_http(backend_url, timeout_seconds=30)
        append_smoke_log(log_path, "backend ready")
        run_command(
            [sys.executable, "scripts/seed_demo_workspace.py", "--idempotent"],
            ROOT_DIR,
            env={
                **backend_env,
                "AB_DB_PATH": str(temp_db_path),
                "AB_HOST": BACKEND_HOST,
                "AB_PORT": str(backend_port),
                "AB_SERVE_FRONTEND_DIST": "true",
                "AB_FRONTEND_DIST_PATH": str(FRONTEND_DIST_DIR),
                "AB_CORS_ORIGINS": "http://127.0.0.1:5173,http://localhost:5173",
                "AB_LLM_TIMEOUT_SECONDS": "1",
                "AB_LLM_MAX_ATTEMPTS": "1",
            },
        )
        append_smoke_log(log_path, "seeded demo workspace")
        run_browser_smoke(
            download_dir=download_dir,
            screenshot_path=screenshot_path,
            failure_dom_path=failure_dom_path,
            backend_url=backend_url,
            api_token=smoke_write_token,
            admin_token=smoke_admin_token,
            log_path=log_path,
        )
    except Exception:
        append_smoke_log(log_path, "smoke run failed")
        terminate_process(backend_process)
        if screenshot_path.exists():
            print(f"Smoke screenshot: {screenshot_path}", file=sys.stderr)
        if failure_dom_path.exists():
            print(f"Smoke DOM dump: {failure_dom_path}", file=sys.stderr)
        raise
    finally:
        terminate_process(backend_process)

    append_smoke_log(log_path, "smoke run passed")
    print(f"Smoke test passed. Downloaded report: {download_dir / 'experiment-report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
