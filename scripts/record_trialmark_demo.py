from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

if TYPE_CHECKING:
    from app.backend.app.evidence.runs import CompletedEvidenceRun
    from app.backend.app.repository import ProjectRepository

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
FRONTEND_DIR = ROOT_DIR / "app" / "frontend"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"
DEMO_DIR = ROOT_DIR / "docs" / "demo"
BACKEND_HOST = "127.0.0.1"
NPM_EXECUTABLE = "npm.cmd" if os.name == "nt" else "npm"
DEFAULT_OUTPUT = DEMO_DIR / "trialmark-workbench-demo.mp4"
DEFAULT_POSTER = DEMO_DIR / "trialmark-workbench-demo.png"
ASOS_FIXTURE_ROOT = (
    ROOT_DIR / "app" / "backend" / "tests" / "fixtures" / "evidence" / "asos"
)


class DemoRecordingError(RuntimeError):
    """Raised when the reproducible recording contract is not met."""


@dataclass(frozen=True)
class DemoRunSelection:
    blocked_run_id: str
    analysis_run_id: str


def seed_recording_blocked_run(
    repository: ProjectRepository,
    *,
    artifact_root: Path,
) -> CompletedEvidenceRun:
    """Persist one genuine ASOS run blocked by an incomplete telemetry contract."""

    from app.backend.app.evidence._common import load_ijson_object
    from app.backend.app.evidence.lifecycle_store import LifecycleEvidenceRunStore
    from app.backend.app.evidence.pipeline import run_protocol
    from app.backend.app.evidence.protocol_io import freeze
    from app.backend.app.evidence.run_abx import materialize_completed_run_logical_abx

    experiment_id = "d53f0e"
    with zipfile.ZipFile(
        ASOS_FIXTURE_ROOT / "bundles" / f"{experiment_id}.tmk"
    ) as archive:
        protocol = load_ijson_object(archive.read("protocol/protocol.json"))
    analysis = cast(dict[str, Any], protocol["analysis"])
    analysis["method"] = {
        "method_id": "binary_pooled_z_newcombe",
        "method_version": "binary_pooled_z_newcombe_v1",
    }
    analysis["random_seed"] = 20260901
    estimand = cast(dict[str, Any], protocol["estimand"])
    estimand["effect_measure"] = "risk_difference"
    for intervention in cast(list[dict[str, Any]], protocol["interventions"]):
        intervention["hash_version"] = "assignment_v1"
    telemetry = cast(dict[str, Any], protocol["telemetry"])
    telemetry["schema_versions"] = [
        schema
        for schema in cast(list[dict[str, Any]], telemetry["schema_versions"])
        if schema["event_type"] != "aggregate_metric_checkpoint"
    ]

    store = LifecycleEvidenceRunStore(repository, artifact_root)
    run = run_protocol(
        freeze(protocol),
        ASOS_FIXTURE_ROOT / f"{experiment_id}.parquet",
        principal="demo-recorder",
        out_store=store,
    )
    if run.kind != "preflight" or not any(
        artifact.role == "finding" for artifact in run.artifacts
    ):
        raise DemoRecordingError("The recording preflight fixture did not block.")
    logical = materialize_completed_run_logical_abx(run)
    store.complete(
        run,
        bundle_id=logical.bundle_id,
        artifact_ref=f"/api/v2/runs/{run.run_id}:bundle",
    )
    return run


def _document_list(document: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = document.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def select_demo_runs(
    portfolio: Mapping[str, Any],
    details: Mapping[str, Mapping[str, Any]],
    *,
    preferred_blocked_run_id: str | None = None,
) -> DemoRunSelection:
    """Select one real blocked run and one successful analysis from the seed."""

    blocked_run_id: str | None = None
    analysis_run_id: str | None = None
    for summary in _document_list(portfolio, "runs"):
        run_id = summary.get("run_id")
        if not isinstance(run_id, str):
            continue
        detail = details.get(run_id, {})
        findings = _document_list(detail, "findings")
        estimates = _document_list(detail, "estimates")
        if summary.get("kind") == "preflight" and any(
            finding.get("state") == "open" for finding in findings
        ):
            if preferred_blocked_run_id is None and blocked_run_id is None:
                blocked_run_id = run_id
            elif run_id == preferred_blocked_run_id:
                blocked_run_id = run_id
        if (
            analysis_run_id is None
            and summary.get("kind") == "analysis"
            and summary.get("status") == "succeeded"
            and estimates
        ):
            analysis_run_id = run_id

    if blocked_run_id is None:
        raise DemoRecordingError("The demo seed does not contain a blocked ASOS run.")
    if analysis_run_id is None:
        raise DemoRecordingError(
            "The demo seed does not contain a succeeded ASOS analysis run."
        )
    return DemoRunSelection(
        blocked_run_id=blocked_run_id,
        analysis_run_id=analysis_run_id,
    )


def _run_command(
    command: Sequence[str],
    *,
    workdir: Path,
    environment: Mapping[str, str] | None = None,
    timeout_seconds: int = 180,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=workdir,
        env=dict(environment) if environment is not None else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=timeout_seconds,
    )


def _choose_backend_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind((BACKEND_HOST, 0))
        return int(candidate.getsockname()[1])


def _wait_for_http(url: str, timeout_seconds: float) -> None:
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
    raise DemoRecordingError(f"Timed out waiting for {url}.")


def _load_json(url: str) -> Mapping[str, Any]:
    with urlopen(url, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, Mapping):
        raise DemoRecordingError(f"Expected an object from {url}.")
    return cast(Mapping[str, Any], payload)


def _load_demo_selection(
    backend_url: str,
    *,
    preferred_blocked_run_id: str | None = None,
) -> DemoRunSelection:
    portfolio = _load_json(f"{backend_url}/api/v2/runs")
    details: dict[str, Mapping[str, Any]] = {}
    for summary in _document_list(portfolio, "runs"):
        run_id = summary.get("run_id")
        if isinstance(run_id, str):
            details[run_id] = _load_json(f"{backend_url}/api/v2/runs/{run_id}")
    return select_demo_runs(
        portfolio,
        details,
        preferred_blocked_run_id=preferred_blocked_run_id,
    )


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _verify_bundle(bundle_path: Path, environment: Mapping[str, str]) -> Mapping[str, Any]:
    result = _run_command(
        [
            sys.executable,
            "-m",
            "app.backend.app.evidence.cli",
            "verify",
            str(bundle_path),
            "--offline",
            "--policy",
            "strict",
        ],
        workdir=ROOT_DIR,
        environment=environment,
        timeout_seconds=120,
    )
    if result.returncode != 0:
        detail = result.stdout.strip() or result.stderr.strip() or "no output"
        raise DemoRecordingError(
            f"Strict offline verification failed for {bundle_path.name}: {detail}"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise DemoRecordingError(
            f"Verifier returned invalid JSON for {bundle_path.name}."
        ) from error
    if not isinstance(payload, Mapping) or payload.get("valid") is not True:
        raise DemoRecordingError(
            f"Verifier did not accept {bundle_path.name}: {payload!r}"
        )
    return cast(Mapping[str, Any], payload)


def _pause(page: Page, milliseconds: int = 1800) -> None:
    page.wait_for_timeout(milliseconds)


def _open_run(page: Page, backend_url: str, run_id: str) -> None:
    page.goto(f"{backend_url}/runs/{run_id}", wait_until="networkidle")
    page.get_by_role("heading", name="Reviewable evidence state").wait_for()


def _capture_poster(page: Page, poster_path: Path) -> None:
    page.evaluate("window.scrollTo({ top: 0, left: 0, behavior: 'instant' })")
    page.screenshot(
        path=str(poster_path),
        animations="disabled",
    )


def _record_browser_flow(
    browser: Browser,
    *,
    backend_url: str,
    run_dir: Path,
    poster_path: Path,
    selection: DemoRunSelection,
    verification_environment: Mapping[str, str],
) -> tuple[Path, Mapping[str, Any], Mapping[str, Any]]:
    video_dir = run_dir / "video"
    download_dir = run_dir / "downloads"
    video_dir.mkdir(parents=True, exist_ok=True)
    download_dir.mkdir(parents=True, exist_ok=True)
    context: BrowserContext = browser.new_context(
        viewport={"width": 1440, "height": 900},
        record_video_dir=str(video_dir),
        record_video_size={"width": 1440, "height": 900},
        accept_downloads=True,
        color_scheme="light",
    )
    page = context.new_page()
    page.route(
        "https://fonts.googleapis.com/**",
        lambda route: route.fulfill(content_type="text/css", body=""),
    )
    page.route("https://fonts.gstatic.com/**", lambda route: route.fulfill(status=204))
    video = page.video
    if video is None:
        raise DemoRecordingError("Playwright did not attach a video recorder.")

    analysis_verification: Mapping[str, Any]
    decision_verification: Mapping[str, Any]
    try:
        page.goto(f"{backend_url}/runs", wait_until="networkidle")
        page.get_by_role("heading", name="Evidence runs").wait_for()
        _pause(page, 2200)

        page.get_by_role(
            "link", name=selection.blocked_run_id, exact=True
        ).click()
        page.get_by_role("heading", name="Reviewable evidence state").wait_for()
        open_state = page.get_by_text("open", exact=True).first
        open_state.scroll_into_view_if_needed()
        _pause(page, 2600)
        remediation_button = page.get_by_role(
            "button", name=re.compile(r"^Mark .+ remediated$")
        )
        remediation_button.click()
        page.get_by_text("resolved", exact=True).first.wait_for()
        _pause(page, 2600)

        _open_run(page, backend_url, selection.analysis_run_id)
        page.get_by_text("No persisted findings", exact=True).scroll_into_view_if_needed()
        _pause(page, 2200)
        estimate_panel = page.get_by_role("region", name="Effect estimates")
        estimate_panel.scroll_into_view_if_needed()
        _pause(page, 2500)

        bundle_heading = page.get_by_role("heading", name="Trialmark bundle")
        bundle_heading.scroll_into_view_if_needed()
        _pause(page, 2400)
        analysis_bundle = download_dir / "analysis.tmk"
        with page.expect_download() as download_info:
            page.get_by_role("button", name="Download .tmk").click()
        download_info.value.save_as(analysis_bundle)
        analysis_verification = _verify_bundle(
            analysis_bundle, verification_environment
        )
        _pause(page, 1800)

        rationale = "The content-bound ASOS evidence supports this benchmark decision."
        decision_heading = page.get_by_role("heading", name="Record decision")
        decision_heading.scroll_into_view_if_needed()
        page.get_by_label("Verdict").select_option("ship")
        page.get_by_label("Rationale").fill(rationale)
        _pause(page, 1800)
        page.get_by_role("button", name="Record human decision").click()
        page.get_by_role("heading", name="Decision record").wait_for()
        page.get_by_text(rationale, exact=True).wait_for()
        _pause(page, 2600)

        bundle_heading = page.get_by_role("heading", name="Trialmark bundle")
        bundle_heading.scroll_into_view_if_needed()
        page.get_by_text("pass", exact=True).first.wait_for()
        _pause(page, 2200)
        decision_bundle = download_dir / "decision.tmk"
        with page.expect_download() as download_info:
            page.get_by_role("button", name="Download .tmk").click()
        download_info.value.save_as(decision_bundle)
        decision_verification = _verify_bundle(
            decision_bundle, verification_environment
        )
        _pause(page, 1800)

        page.get_by_role("heading", name="Decision record").scroll_into_view_if_needed()
        _pause(page, 1800)
        _capture_poster(page, poster_path)
    finally:
        page.close()
        context.close()

    return Path(video.path()), analysis_verification, decision_verification


def _transcode_video(source: Path, destination: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise DemoRecordingError(
            "ffmpeg is required to create the MP4 demo; install it or add it to PATH."
        )
    temporary = destination.with_name(f"{destination.stem}.tmp{destination.suffix}")
    result = _run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "25",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(temporary),
        ],
        workdir=ROOT_DIR,
        timeout_seconds=180,
    )
    if result.returncode != 0 or not temporary.exists():
        temporary.unlink(missing_ok=True)
        detail = result.stderr.strip() or result.stdout.strip() or "no output"
        raise DemoRecordingError(f"ffmpeg failed to create the demo: {detail}")
    temporary.replace(destination)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record the real Trialmark ASOS workbench flow as an MP4."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--poster", type=Path, default=DEFAULT_POSTER)
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Use the existing app/frontend/dist build.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing generated video and poster files.",
    )
    return parser.parse_args()


def main() -> int:
    from app.backend.app.repository import ProjectRepository

    args = _parse_args()
    output_path = args.output.resolve()
    poster_path = args.poster.resolve()
    existing = [path for path in (output_path, poster_path) if path.exists()]
    if existing and not args.force:
        names = ", ".join(str(path) for path in existing)
        raise DemoRecordingError(f"Refusing to replace existing output: {names}")

    if not args.skip_build:
        build = _run_command(
            [NPM_EXECUTABLE, "run", "build"],
            workdir=FRONTEND_DIR,
            timeout_seconds=180,
        )
        if build.returncode != 0:
            detail = build.stdout.strip() or build.stderr.strip() or "no output"
            raise DemoRecordingError(f"Frontend build failed: {detail}")
    if not (FRONTEND_DIST_DIR / "index.html").exists():
        raise DemoRecordingError(
            "Frontend dist is missing. Run the recorder without --skip-build first."
        )

    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    run_dir = ROOT_DIR / "archive" / "demo-runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    poster_path.parent.mkdir(parents=True, exist_ok=True)
    backend_port = _choose_backend_port()
    backend_url = f"http://{BACKEND_HOST}:{backend_port}"
    backend_environment = os.environ.copy()
    backend_environment.pop("AB_DATABASE_URL", None)
    for name in ("AB_API_TOKEN", "AB_READONLY_API_TOKEN", "AB_ADMIN_TOKEN"):
        backend_environment.pop(name, None)
    backend_environment.update(
        {
            "AB_DB_PATH": str(run_dir / "trialmark.sqlite3"),
            "AB_ENV": "demo-recording",
            "AB_HOST": BACKEND_HOST,
            "AB_PORT": str(backend_port),
            "AB_SEED_DEMO_ON_STARTUP": "true",
            "AB_SERVE_FRONTEND_DIST": "true",
            "AB_FRONTEND_DIST_PATH": str(FRONTEND_DIST_DIR),
        }
    )
    repository = ProjectRepository(
        f"sqlite:///{(run_dir / 'trialmark.sqlite3').as_posix()}"
    )
    try:
        recording_blocked_run = seed_recording_blocked_run(
            repository,
            artifact_root=run_dir / ".trialmark" / "artifacts",
        )
    finally:
        repository.close()
    backend_log_path = run_dir / "backend.log"
    with backend_log_path.open("w", encoding="utf-8") as backend_log:
        backend_process = subprocess.Popen(
            [sys.executable, str(ROOT_DIR / "scripts" / "run_backend_for_e2e.py")],
            cwd=run_dir,
            env=backend_environment,
            stdout=backend_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            _wait_for_http(f"{backend_url}/health", timeout_seconds=30)
            _wait_for_http(f"{backend_url}/runs", timeout_seconds=30)
            selection = _load_demo_selection(
                backend_url,
                preferred_blocked_run_id=recording_blocked_run.run_id,
            )
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    source_video, analysis_verification, decision_verification = (
                        _record_browser_flow(
                            browser,
                            backend_url=backend_url,
                            run_dir=run_dir,
                            poster_path=poster_path,
                            selection=selection,
                            verification_environment=backend_environment,
                        )
                    )
                finally:
                    browser.close()
        finally:
            _terminate_process(backend_process)

    _transcode_video(source_video, output_path)
    summary = {
        "valid": True,
        "output": str(output_path),
        "poster": str(poster_path),
        "run_dir": str(run_dir),
        "blocked_run_id": selection.blocked_run_id,
        "analysis_run_id": selection.analysis_run_id,
        "analysis_bundle_id": analysis_verification.get("bundle_id"),
        "decision_bundle_id": decision_verification.get("bundle_id"),
        "analysis_verdicts": analysis_verification.get("verdicts"),
        "decision_verdicts": decision_verification.get("verdicts"),
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
