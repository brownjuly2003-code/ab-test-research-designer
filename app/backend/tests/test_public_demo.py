"""Public demo mode (AB_PUBLIC_DEMO): anonymous read scope + stateless compute.

The hosted demo grants anonymous visitors a read-scope session instead of a 401:
they can browse saved projects and use every stateless calculator, but every
repository mutation requires a write-capable token, and server-funded LLM calls
(the Mistral insurance key / local orchestrator) are reserved for write/admin
sessions — guests must bring their own provider key.
"""

from pathlib import Path
import sys
import uuid

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.config import get_settings
from app.backend.app.http_utils import PUBLIC_COMPUTE_PATHS
from app.backend.app.llm.adapter import LocalOrchestratorAdapter
from app.backend.app.llm.mistral_adapter import MistralAdapter
from app.backend.app.llm.openai_adapter import OpenAIAdapter
from app.backend.app.main import create_app

WRITE_TOKEN = "super-secret-token"
WRITE_HEADERS = {"Authorization": f"Bearer {WRITE_TOKEN}"}


def _enable_public_demo(monkeypatch, *, write_token: bool = True) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("AB_DB_PATH", str(temp_dir / f"{uuid.uuid4()}.sqlite3"))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    monkeypatch.setenv("AB_PUBLIC_DEMO", "true")
    if write_token:
        monkeypatch.setenv("AB_API_TOKEN", WRITE_TOKEN)
    get_settings.cache_clear()


def _calculate_body() -> dict:
    return {
        "metric_type": "binary",
        "baseline_value": 0.042,
        "mde_pct": 5,
        "alpha": 0.05,
        "power": 0.8,
        "expected_daily_traffic": 12000,
        "audience_share_in_test": 1.0,
        "traffic_split": [50, 50],
        "variants_count": 2,
    }


def _experiment_payload() -> dict:
    return {
        "project": {
            "project_name": "Checkout redesign",
            "domain": "e-commerce",
            "product_type": "web app",
            "platform": "web",
            "market": "US",
            "project_description": "We want to test a simplified checkout flow.",
        },
        "hypothesis": {
            "change_description": "Reduce checkout from 4 steps to 2",
            "target_audience": "new users on web",
            "business_problem": "checkout abandonment is high",
            "hypothesis_statement": "If we simplify checkout, conversion will increase.",
            "what_to_validate": "impact on conversion",
            "desired_result": "statistically meaningful uplift",
        },
        "setup": {
            "experiment_type": "ab",
            "randomization_unit": "user",
            "traffic_split": [50, 50],
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "variants_count": 2,
            "inclusion_criteria": "new users only",
            "exclusion_criteria": "internal staff",
        },
        "metrics": {
            "primary_metric_name": "purchase_conversion",
            "metric_type": "binary",
            "baseline_value": 0.042,
            "expected_uplift_pct": 8,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "std_dev": None,
            "secondary_metrics": [],
            "guardrail_metrics": [],
        },
        "constraints": {
            "seasonality_present": True,
            "active_campaigns_present": False,
            "returning_users_present": True,
            "interference_risk": "medium",
            "technical_constraints": "legacy event logging",
            "legal_or_ethics_constraints": "none",
            "known_risks": "tracking quality",
            "deadline_pressure": "medium",
            "long_test_possible": True,
        },
        "additional_context": {},
    }


def test_public_demo_grants_anonymous_read_and_compute(monkeypatch) -> None:
    _enable_public_demo(monkeypatch)

    with TestClient(create_app()) as client:
        projects = client.get("/api/v1/projects")
        calculated = client.post("/api/v1/calculate", json=_calculate_body())
        diagnostics = client.get("/api/v1/diagnostics")

    assert projects.status_code == 200
    assert calculated.status_code == 200
    assert calculated.json()["results"]["sample_size_per_variant"] > 0
    assert diagnostics.status_code == 200
    auth = diagnostics.json()["auth"]
    assert auth["enabled"] is True
    assert auth["public_demo"] is True
    assert auth["session_scope"] == "read"
    assert auth["session_source"] == "anonymous"
    assert auth["session_can_write"] is False
    get_settings.cache_clear()


def test_public_demo_every_compute_path_admits_anonymous_post(monkeypatch) -> None:
    """Middleware whitelist and route guards must stay in sync.

    An anonymous POST to every PUBLIC_COMPUTE_PATHS entry must reach the handler
    (422/400/200 on an empty body) instead of being rejected by auth (401/403).
    A path listed in the whitelist but still guarded by require_write_auth would
    fail here with 403.
    """
    _enable_public_demo(monkeypatch)

    with TestClient(create_app()) as client:
        for path in sorted(PUBLIC_COMPUTE_PATHS):
            response = client.post(path, json={})
            assert response.status_code not in (401, 403), (
                f"{path} rejected an anonymous compute POST with {response.status_code}"
            )
    get_settings.cache_clear()


def test_every_read_scope_compute_route_is_whitelisted(monkeypatch) -> None:
    """The reverse direction of the sync invariant.

    Every fixed-path POST route guarded by require_auth (read scope) is by
    definition a stateless compute endpoint, so it must also appear in
    PUBLIC_COMPUTE_PATHS — otherwise the middleware rejects anonymous demo
    sessions with 403 before the (willing) route guard is ever consulted.
    This is exactly how /results/survival and /results/ratio shipped broken
    on the public Space: correct route guard, missing whitelist entry.
    """
    _enable_public_demo(monkeypatch)

    app = create_app()
    missing: list[str] = []
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        dependant = getattr(route, "dependant", None)
        if "POST" not in methods or not path.startswith("/api/v1") or "{" in path:
            continue
        guard_names = {
            dep.call.__name__ for dep in getattr(dependant, "dependencies", []) if dep.call is not None
        }
        if "require_auth" in guard_names and path not in PUBLIC_COMPUTE_PATHS:
            missing.append(path)
    assert not missing, (
        "POST routes guarded by require_auth are missing from PUBLIC_COMPUTE_PATHS "
        f"(anonymous demo sessions would get 403 from the middleware): {sorted(missing)}"
    )
    get_settings.cache_clear()


def test_public_demo_blocks_anonymous_mutations(monkeypatch) -> None:
    _enable_public_demo(monkeypatch)

    with TestClient(create_app()) as client:
        created = client.post("/api/v1/projects", json=_experiment_payload(), headers=WRITE_HEADERS)
        assert created.status_code == 200
        project_id = created.json()["id"]

        anon_create = client.post("/api/v1/projects", json=_experiment_payload())
        anon_delete = client.delete(f"/api/v1/projects/{project_id}")
        anon_archive = client.post(f"/api/v1/projects/{project_id}/archive")
        anon_template = client.post(
            "/api/v1/templates",
            json={"name": "T", "description": "d", "payload": _experiment_payload()},
        )
        anon_keys = client.get("/api/v1/keys")
        still_there = client.get(f"/api/v1/projects/{project_id}")

    assert anon_create.status_code == 403
    assert anon_delete.status_code == 403
    assert anon_archive.status_code == 403
    assert anon_template.status_code == 403
    # keys/webhooks are admin-only surfaces: no anonymous read scope there.
    assert anon_keys.status_code == 401
    assert still_there.status_code == 200
    get_settings.cache_clear()


def test_public_demo_write_token_still_mutates(monkeypatch) -> None:
    _enable_public_demo(monkeypatch)

    with TestClient(create_app()) as client:
        created = client.post("/api/v1/projects", json=_experiment_payload(), headers=WRITE_HEADERS)
        assert created.status_code == 200
        project_id = created.json()["id"]
        deleted = client.delete(f"/api/v1/projects/{project_id}", headers=WRITE_HEADERS)

    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    get_settings.cache_clear()


def test_public_demo_anonymous_analyze_never_spends_server_llm(monkeypatch) -> None:
    _enable_public_demo(monkeypatch)
    monkeypatch.setenv("AB_MISTRAL_API_KEY", "server-mistral-key")
    get_settings.cache_clear()

    llm_calls: list[str] = []
    monkeypatch.setattr(
        LocalOrchestratorAdapter,
        "request_advice",
        lambda self, payload: llm_calls.append("local")
        or {
            "available": False,
            "provider": "local_orchestrator",
            "model": "offline",
            "advice": None,
            "raw_text": None,
            "error": "unavailable",
            "error_code": None,
        },
    )
    monkeypatch.setattr(
        MistralAdapter,
        "request_advice",
        lambda self, payload, token=None: llm_calls.append("mistral")
        or {
            "available": True,
            "provider": "mistral",
            "model": "mistral-small-latest",
            "advice": None,
            "raw_text": "insured advice",
            "error": None,
            "error_code": None,
        },
    )

    with TestClient(create_app()) as client:
        anonymous = client.post("/api/v1/analyze", json=_experiment_payload())
        assert anonymous.status_code == 200
        anon_advice = anonymous.json()["advice"]
        assert llm_calls == []
        assert anon_advice["available"] is False
        assert anon_advice["error_code"] == "public_demo_llm_requires_key"

        # A write session keeps the server-funded path: local first, Mistral insurance after.
        authenticated = client.post("/api/v1/analyze", json=_experiment_payload(), headers=WRITE_HEADERS)
        assert authenticated.status_code == 200
        assert llm_calls == ["local", "mistral"]
        assert authenticated.json()["advice"]["provider"] == "mistral"
    get_settings.cache_clear()


def test_public_demo_anonymous_analyze_honors_byo_key(monkeypatch) -> None:
    _enable_public_demo(monkeypatch)

    byo_calls: list[str] = []
    monkeypatch.setattr(
        OpenAIAdapter,
        "request_advice",
        lambda self, payload, token=None: byo_calls.append(token)
        or {
            "available": True,
            "provider": "openai",
            "model": "gpt-test",
            "advice": None,
            "raw_text": "byo advice",
            "error": None,
            "error_code": None,
        },
    )

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/analyze",
            json=_experiment_payload(),
            headers={"X-AB-LLM-Provider": "openai", "X-AB-LLM-Token": "guest-own-key"},
        )

    assert response.status_code == 200
    assert byo_calls == ["guest-own-key"]
    assert response.json()["advice"]["provider"] == "openai"
    assert response.json()["advice"]["available"] is True
    get_settings.cache_clear()


def test_public_demo_disabled_keeps_anonymous_locked_out(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("AB_DB_PATH", str(temp_dir / f"{uuid.uuid4()}.sqlite3"))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    monkeypatch.setenv("AB_API_TOKEN", WRITE_TOKEN)
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        projects = client.get("/api/v1/projects")
        calculated = client.post("/api/v1/calculate", json=_calculate_body())

    assert projects.status_code == 401
    assert calculated.status_code == 401
    get_settings.cache_clear()


def test_public_demo_without_tokens_still_forces_read_only(monkeypatch) -> None:
    """AB_PUBLIC_DEMO alone (no tokens at all) must never expose open mutations."""
    _enable_public_demo(monkeypatch, write_token=False)

    with TestClient(create_app()) as client:
        projects = client.get("/api/v1/projects")
        calculated = client.post("/api/v1/calculate", json=_calculate_body())
        anon_create = client.post("/api/v1/projects", json=_experiment_payload())

    assert projects.status_code == 200
    assert calculated.status_code == 200
    assert anon_create.status_code == 403
    get_settings.cache_clear()


def test_readonly_token_gains_stateless_compute(monkeypatch) -> None:
    """Read scope means "cannot change stored state", not "GET only" — the readonly
    token may now run the stateless calculators while mutations stay 403."""
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("AB_DB_PATH", str(temp_dir / f"{uuid.uuid4()}.sqlite3"))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    monkeypatch.setenv("AB_API_TOKEN", WRITE_TOKEN)
    monkeypatch.setenv("AB_READONLY_API_TOKEN", "readonly-secret")
    get_settings.cache_clear()

    readonly_headers = {"Authorization": "Bearer readonly-secret"}
    with TestClient(create_app()) as client:
        calculated = client.post("/api/v1/calculate", json=_calculate_body(), headers=readonly_headers)
        mutated = client.post("/api/v1/projects", json=_experiment_payload(), headers=readonly_headers)

    assert calculated.status_code == 200
    assert mutated.status_code == 403
    get_settings.cache_clear()
