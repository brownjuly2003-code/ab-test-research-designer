import sys
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.config import get_settings
from app.backend.app.main import create_app
from app.backend.app.slack.signature import build_slack_signature


def _configure_slack(monkeypatch, db_path: Path) -> None:
    monkeypatch.setenv("AB_DB_PATH", str(db_path))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    monkeypatch.setenv("AB_SLACK_CLIENT_ID", "111.222")
    monkeypatch.setenv("AB_SLACK_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("AB_SLACK_SIGNING_SECRET", "signing-secret")
    get_settings.cache_clear()


def _signed_headers(body: bytes, *, timestamp: str | None = None) -> dict[str, str]:
    timestamp = timestamp or str(int(time.time()))
    return {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": build_slack_signature("signing-secret", timestamp, body),
        "Content-Type": "application/x-www-form-urlencoded",
    }


def _signed_json_headers(body: bytes, *, timestamp: str | None = None) -> dict[str, str]:
    headers = _signed_headers(body, timestamp=timestamp)
    headers["Content-Type"] = "application/json"
    return headers


def test_slack_routes_return_503_when_not_configured(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("AB_DB_PATH", str(temp_dir / f"{uuid.uuid4()}.sqlite3"))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    monkeypatch.delenv("AB_SLACK_CLIENT_ID", raising=False)
    monkeypatch.delenv("AB_SLACK_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("AB_SLACK_SIGNING_SECRET", raising=False)
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.get("/slack/install")

    assert response.status_code == 503
    assert response.json()["error"] == "slack_not_configured"
    get_settings.cache_clear()


def test_slack_install_redirects_with_state(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    _configure_slack(monkeypatch, temp_dir / f"{uuid.uuid4()}.sqlite3")

    with TestClient(create_app()) as client:
        response = client.get("/slack/install", follow_redirects=False)

    assert response.status_code == 307
    location = response.headers["location"]
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert parsed.netloc == "slack.com"
    assert query["client_id"] == ["111.222"]
    assert "commands" in query["scope"][0]
    assert query["state"][0]
    get_settings.cache_clear()


def test_slack_oauth_callback_stores_installation(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    _configure_slack(monkeypatch, temp_dir / f"{uuid.uuid4()}.sqlite3")

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://slack.com/api/oauth.v2.access"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "team": {"id": "T123", "name": "Example"},
                "access_token": "xoxb-token",
                "authed_user": {"access_token": "xoxp-user"},
            },
        )

    app = create_app()
    app.state.slack_http_client = httpx.Client(transport=httpx.MockTransport(handler))
    with TestClient(app) as client:
        install = client.get("/slack/install", follow_redirects=False)
        state = parse_qs(urlparse(install.headers["location"]).query)["state"][0]
        response = client.get(f"/slack/oauth/callback?code=abc&state={state}")
        status = client.get("/api/v1/slack/status")

    assert response.status_code == 200
    assert status.json()["installed"] is True
    assert status.json()["team_id"] == "T123"
    get_settings.cache_clear()


def test_slack_command_rejects_bad_signature(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    _configure_slack(monkeypatch, temp_dir / f"{uuid.uuid4()}.sqlite3")

    body = b"team_id=T123&text=projects&response_url=https%3A%2F%2Fexample.com"
    headers = _signed_headers(body)
    headers["X-Slack-Signature"] = "v0=bad"

    with TestClient(create_app()) as client:
        response = client.post("/slack/commands", content=body, headers=headers)

    assert response.status_code == 401
    get_settings.cache_clear()


def test_slack_events_rejects_bad_signature(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    _configure_slack(monkeypatch, temp_dir / f"{uuid.uuid4()}.sqlite3")

    body = b'{"type":"url_verification","challenge":"abc"}'
    headers = _signed_json_headers(body)
    headers["X-Slack-Signature"] = "v0=bad"

    with TestClient(create_app()) as client:
        response = client.post("/slack/events", content=body, headers=headers)

    assert response.status_code == 401
    get_settings.cache_clear()


def test_slack_events_answers_signed_url_verification(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    _configure_slack(monkeypatch, temp_dir / f"{uuid.uuid4()}.sqlite3")

    body = b'{"type":"url_verification","challenge":"abc"}'
    headers = _signed_json_headers(body)

    with TestClient(create_app()) as client:
        response = client.post("/slack/events", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json()["challenge"] == "abc"
    get_settings.cache_clear()


def test_slack_projects_command_returns_ephemeral_list(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    _configure_slack(monkeypatch, temp_dir / f"{uuid.uuid4()}.sqlite3")
    body = b"team_id=T123&text=projects&response_url=https%3A%2F%2Fexample.com"

    with TestClient(create_app()) as client:
        created = client.post(
            "/api/v1/projects",
            json={
                "project": {
                    "project_name": "Checkout redesign",
                    "domain": "e-commerce",
                    "product_type": "web app",
                    "platform": "web",
                    "market": "US",
                    "project_description": "Test checkout.",
                },
                "hypothesis": {
                    "change_description": "Shorter checkout",
                    "target_audience": "new users",
                    "business_problem": "Dropoff",
                    "hypothesis_statement": "Shorter checkout improves conversion.",
                    "what_to_validate": "Conversion",
                    "desired_result": "Uplift",
                },
                "setup": {
                    "experiment_type": "ab",
                    "randomization_unit": "user",
                    "traffic_split": [50, 50],
                    "expected_daily_traffic": 1000,
                    "audience_share_in_test": 1,
                    "variants_count": 2,
                    "inclusion_criteria": "",
                    "exclusion_criteria": "",
                },
                "metrics": {
                    "primary_metric_name": "conversion",
                    "metric_type": "binary",
                    "baseline_value": 0.1,
                    "expected_uplift_pct": 5,
                    "mde_pct": 5,
                    "alpha": 0.05,
                    "power": 0.8,
                    "std_dev": None,
                    "secondary_metrics": [],
                    "guardrail_metrics": [],
                },
                "constraints": {
                    "seasonality_present": False,
                    "active_campaigns_present": False,
                    "returning_users_present": False,
                    "interference_risk": "low",
                    "technical_constraints": "",
                    "legal_or_ethics_constraints": "",
                    "known_risks": "",
                    "deadline_pressure": "low",
                    "long_test_possible": True,
                },
                "additional_context": {"llm_context": ""},
            },
        )
        assert created.status_code == 200
        response = client.post("/slack/commands", content=body, headers=_signed_headers(body))

    assert response.status_code == 200
    payload = response.json()
    assert payload["response_type"] == "ephemeral"
    assert "Checkout redesign" in payload["text"]
    get_settings.cache_clear()

def test_slack_commands_reject_oversized_body_with_content_length(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    _configure_slack(monkeypatch, temp_dir / f"{uuid.uuid4()}.sqlite3")
    monkeypatch.setenv("AB_MAX_SLACK_BODY_BYTES", "2048")
    get_settings.cache_clear()

    body = b"team_id=T123&text=" + (b"x" * 3000)
    headers = _signed_headers(body)
    # Correct Content-Length above cap must 413 before signature work matters.
    headers["Content-Length"] = str(len(body))

    with TestClient(create_app()) as client:
        response = client.post("/slack/commands", content=body, headers=headers)

    assert response.status_code == 413
    assert response.json()["error_code"] == "request_body_too_large"
    get_settings.cache_clear()


def test_slack_commands_reject_body_exceeding_cap_despite_small_content_length(monkeypatch) -> None:
    """Chunked / lying Content-Length: middleware counts actual bytes (audit F-05)."""
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    _configure_slack(monkeypatch, temp_dir / f"{uuid.uuid4()}.sqlite3")
    monkeypatch.setenv("AB_MAX_SLACK_BODY_BYTES", "1024")
    get_settings.cache_clear()

    body = b"team_id=T123&text=" + (b"y" * 2000)
    headers = _signed_headers(body)
    # Under-declared Content-Length must not bypass the streaming byte cap.
    headers["Content-Length"] = "64"

    with TestClient(create_app()) as client:
        response = client.post("/slack/commands", content=body, headers=headers)

    # Starlette/TestClient may reject mismatched Content-Length with 400 before our
    # middleware; either way the oversized body must not reach the Slack handler.
    assert response.status_code in {400, 413}
    if response.status_code == 413:
        assert response.json()["error_code"] == "request_body_too_large"
    get_settings.cache_clear()


def test_slack_invalid_signature_burst_is_rate_limited(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    _configure_slack(monkeypatch, temp_dir / f"{uuid.uuid4()}.sqlite3")
    monkeypatch.setenv("AB_SLACK_INVALID_SIGNATURE_LIMIT", "2")
    monkeypatch.setenv("AB_SLACK_INVALID_SIGNATURE_WINDOW_SECONDS", "60")
    monkeypatch.setenv("AB_SLACK_RATE_LIMIT_REQUESTS", "100")
    get_settings.cache_clear()

    body = b"team_id=T123&text=projects"
    headers = _signed_headers(body)
    headers["X-Slack-Signature"] = "v0=bad"

    with TestClient(create_app()) as client:
        first = client.post("/slack/commands", content=body, headers=headers)
        second = client.post("/slack/commands", content=body, headers=headers)
        third = client.post("/slack/commands", content=body, headers=headers)

    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429
    assert third.json()["error_code"] == "slack_invalid_signature_rate_limited"
    assert int(third.headers["retry-after"]) >= 1
    get_settings.cache_clear()


def test_slack_valid_signed_retry_still_succeeds_after_invalid_burst(monkeypatch) -> None:
    """Valid Slack retries (correct signature) must not be poisoned by bad-sig throttle."""
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    _configure_slack(monkeypatch, temp_dir / f"{uuid.uuid4()}.sqlite3")
    monkeypatch.setenv("AB_SLACK_INVALID_SIGNATURE_LIMIT", "1")
    monkeypatch.setenv("AB_SLACK_RATE_LIMIT_REQUESTS", "100")
    get_settings.cache_clear()

    body = b"team_id=T123&text=projects"
    bad_headers = _signed_headers(body)
    bad_headers["X-Slack-Signature"] = "v0=bad"
    good_headers = _signed_headers(body)

    with TestClient(create_app()) as client:
        assert client.post("/slack/commands", content=body, headers=bad_headers).status_code == 401
        # Second bad signature is rate-limited.
        assert client.post("/slack/commands", content=body, headers=bad_headers).status_code == 429
        # A correctly signed retry (Slack retry semantics) still works.
        ok = client.post("/slack/commands", content=body, headers=good_headers)

    assert ok.status_code == 200
    assert ok.json()["response_type"] == "ephemeral"
    get_settings.cache_clear()
