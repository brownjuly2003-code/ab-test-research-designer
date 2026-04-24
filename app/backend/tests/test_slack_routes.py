from pathlib import Path
import sys
import time
from urllib.parse import parse_qs, urlparse
import uuid

from fastapi.testclient import TestClient
import httpx

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
