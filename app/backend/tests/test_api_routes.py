from pathlib import Path
import sys
import uuid

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import app.backend.app.main as main_module
from app.backend.app.config import get_settings
from app.backend.app.main import create_app
from app.backend.app.llm.adapter import LocalOrchestratorAdapter


def _full_payload() -> dict:
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
            "secondary_metrics": ["add_to_cart_rate"],
            "guardrail_metrics": ["payment_error_rate", "refund_rate"],
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
        "additional_context": {
            "llm_context": "Previous tests showed mixed results.",
        },
    }


def test_calculate_endpoint_returns_deterministic_payload() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/calculate",
        json={
            "metric_type": "binary",
            "baseline_value": 0.042,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "traffic_split": [50, 50],
            "variants_count": 2,
        },
    )

    assert response.status_code == 200
    assert response.json()["calculation_summary"]["metric_type"] == "binary"
    assert response.json()["bonferroni_note"] is None
    assert response.headers["x-request-id"]
    assert float(response.headers["x-process-time-ms"]) >= 0


def test_calculate_endpoint_surfaces_bonferroni_note_for_multivariant_design() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/calculate",
        json={
            "metric_type": "binary",
            "baseline_value": 0.042,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "traffic_split": [34, 33, 33],
            "variants_count": 3,
        },
    )

    assert response.status_code == 200
    assert response.json()["bonferroni_note"] is not None


def test_design_endpoint_builds_report_without_llm() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/design", json=_full_payload())

    assert response.status_code == 200
    assert response.json()["metrics_plan"]["primary"] == ["purchase_conversion"]


def test_analyze_endpoint_returns_combined_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        LocalOrchestratorAdapter,
        "request_advice",
        lambda self, payload: {
            "available": True,
            "provider": "local_orchestrator",
            "model": "Claude Sonnet 4.6",
            "advice": {
                "brief_assessment": "Combined analysis available.",
                "key_risks": ["Tracking quality"],
                "design_improvements": ["Validate event schema"],
                "metric_recommendations": ["Track checkout step completion"],
                "interpretation_pitfalls": ["Do not stop early"],
                "additional_checks": ["Verify exposure balance"],
            },
            "raw_text": "{\"brief_assessment\": \"Combined analysis available.\"}",
            "error": None,
            "error_code": None,
        },
    )
    client = TestClient(create_app())

    response = client.post("/api/v1/analyze", json=_full_payload())

    assert response.status_code == 200
    payload = response.json()
    assert payload["calculations"]["calculation_summary"]["metric_type"] == "binary"
    assert payload["report"]["metrics_plan"]["primary"] == ["purchase_conversion"]
    assert payload["advice"]["available"] is True
    assert payload["advice"]["advice"]["brief_assessment"] == "Combined analysis available."


def test_llm_advice_endpoint_returns_graceful_fallback_when_orchestrator_unavailable() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/llm/advice", json={"project_context": {"project_name": "Checkout redesign"}})

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["error_code"] is not None


def test_calculate_endpoint_rejects_mismatched_variant_configuration() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/calculate",
        json={
            "metric_type": "binary",
            "baseline_value": 0.042,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "traffic_split": [50, 50],
            "variants_count": 3,
        },
    )

    assert response.status_code == 422
    assert "traffic_split length must match variants_count" in str(response.json()["detail"])
    assert response.json()["error_code"] == "validation_error"
    assert response.json()["status_code"] == 422
    assert response.json()["request_id"]
    assert response.headers["x-error-code"] == "validation_error"


def test_calculate_endpoint_allows_vite_preflight_origin() -> None:
    client = TestClient(create_app())

    response = client.options(
        "/api/v1/calculate",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert response.headers["access-control-allow-methods"] == "GET, POST, PUT, DELETE, OPTIONS"
    assert response.headers["access-control-allow-headers"] == "Accept, Accept-Language, Content-Language, Content-Type"


def test_calculate_endpoint_rejects_too_many_variants() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/calculate",
        json={
            "metric_type": "binary",
            "baseline_value": 0.042,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "traffic_split": [10] * 11,
            "variants_count": 11,
        },
    )

    assert response.status_code == 422
    assert "less than or equal to 10" in str(response.json()["detail"])


def test_calculate_endpoint_rejects_zero_std_dev_for_continuous_metric() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/calculate",
        json={
            "metric_type": "continuous",
            "baseline_value": 15.0,
            "std_dev": 0,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "traffic_split": [50, 50],
            "variants_count": 2,
        },
    )

    assert response.status_code == 422
    assert "std_dev must be positive for continuous metrics" in str(response.json()["detail"])


def test_design_endpoint_returns_internal_error_for_unexpected_exception(monkeypatch) -> None:
    def explode(*args, **kwargs):
        raise KeyError("missing")

    monkeypatch.setattr(main_module, "build_experiment_report", explode)
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post("/api/v1/design", json=_full_payload())

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert response.json()["error_code"] == "internal_error"
    assert response.json()["status_code"] == 500
    assert response.json()["request_id"]


def test_diagnostics_endpoint_returns_runtime_summary(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"

    monkeypatch.setenv("AB_DB_PATH", str(db_path))
    monkeypatch.setenv("AB_ENV", "test")
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    monkeypatch.setenv("AB_LOG_FORMAT", "json")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.get("/api/v1/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["environment"] == "test"
    assert payload["request_timing_headers_enabled"] is True
    assert payload["storage"]["db_path"] == str(db_path)
    assert payload["storage"]["schema_version"] == 2
    assert payload["storage"]["sqlite_user_version"] == 2
    assert payload["storage"]["journal_mode"] == "WAL"
    assert payload["storage"]["synchronous"] == "NORMAL"
    assert payload["storage"]["projects_total"] == 0
    assert payload["storage"]["project_revisions_total"] == 0
    assert payload["frontend"]["serve_frontend_dist"] is False
    assert payload["llm"]["provider"] == "local_orchestrator"
    assert payload["logging"]["format"] == "json"
    assert payload["auth"]["enabled"] is False
    assert payload["auth"]["mode"] == "open"
    assert payload["auth"]["write_enabled"] is False
    assert payload["auth"]["readonly_enabled"] is False
    assert payload["runtime"]["total_requests"] >= 0
    assert payload["runtime"]["success_responses"] >= 0
    assert payload["runtime"]["auth_rejections"] == 0
    assert response.headers["x-request-id"]
    assert float(response.headers["x-process-time-ms"]) >= 0
    get_settings.cache_clear()


def test_readyz_returns_degraded_when_frontend_dist_is_missing(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    missing_frontend_dist = temp_dir / f"{uuid.uuid4()}-missing-dist"

    monkeypatch.setenv("AB_FRONTEND_DIST_PATH", str(missing_frontend_dist))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "true")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "degraded"
    assert any(check["name"] == "frontend_dist" and check["ok"] is False for check in payload["checks"])
    assert any(check["name"] == "sqlite_schema_version" and check["ok"] is True for check in payload["checks"])
    assert any(check["name"] == "sqlite_journal_mode" and check["ok"] is True for check in payload["checks"])
    get_settings.cache_clear()


def test_api_token_protects_runtime_and_api_routes(monkeypatch) -> None:
    monkeypatch.setenv("AB_API_TOKEN", "super-secret-token")
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        health_response = client.get("/health")
        unauthorized_diagnostics = client.get("/api/v1/diagnostics")
        unauthorized_readyz = client.get("/readyz")
        authorized_diagnostics = client.get(
            "/api/v1/diagnostics",
            headers={"Authorization": "Bearer super-secret-token"},
        )
        api_key_diagnostics = client.get(
            "/api/v1/diagnostics",
            headers={"X-API-Key": "super-secret-token"},
        )

    assert health_response.status_code == 200
    assert unauthorized_diagnostics.status_code == 401
    assert unauthorized_diagnostics.json()["detail"] == "Unauthorized"
    assert unauthorized_diagnostics.json()["error_code"] == "unauthorized"
    assert unauthorized_readyz.status_code == 401
    assert authorized_diagnostics.status_code == 200
    assert authorized_diagnostics.json()["auth"]["enabled"] is True
    assert authorized_diagnostics.json()["auth"]["mode"] == "token"
    assert authorized_diagnostics.json()["auth"]["write_enabled"] is True
    assert authorized_diagnostics.json()["auth"]["readonly_enabled"] is False
    assert api_key_diagnostics.status_code == 200
    get_settings.cache_clear()


def test_readonly_api_token_allows_safe_requests_but_blocks_mutations(monkeypatch) -> None:
    monkeypatch.setenv("AB_READONLY_API_TOKEN", "readonly-secret")
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        diagnostics_response = client.get(
            "/api/v1/diagnostics",
            headers={"Authorization": "Bearer readonly-secret"},
        )
        project_list_response = client.get(
            "/api/v1/projects",
            headers={"Authorization": "Bearer readonly-secret"},
        )
        forbidden_calculation = client.post(
            "/api/v1/calculate",
            headers={"Authorization": "Bearer readonly-secret"},
            json={
                "metric_type": "binary",
                "baseline_value": 0.042,
                "mde_pct": 5,
                "alpha": 0.05,
                "power": 0.8,
                "expected_daily_traffic": 12000,
                "audience_share_in_test": 0.6,
                "traffic_split": [50, 50],
                "variants_count": 2,
            },
        )

    assert diagnostics_response.status_code == 200
    assert diagnostics_response.json()["auth"]["mode"] == "readonly"
    assert diagnostics_response.json()["auth"]["write_enabled"] is False
    assert diagnostics_response.json()["auth"]["readonly_enabled"] is True
    assert project_list_response.status_code == 200
    assert forbidden_calculation.status_code == 403
    assert forbidden_calculation.json()["detail"] == "Forbidden"
    assert forbidden_calculation.json()["error_code"] == "forbidden"
    get_settings.cache_clear()


def test_dual_token_auth_mode_reports_both_scopes(monkeypatch) -> None:
    monkeypatch.setenv("AB_API_TOKEN", "super-secret-token")
    monkeypatch.setenv("AB_READONLY_API_TOKEN", "readonly-secret")
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        diagnostics_response = client.get(
            "/api/v1/diagnostics",
            headers={"Authorization": "Bearer super-secret-token"},
        )

    assert diagnostics_response.status_code == 200
    assert diagnostics_response.json()["auth"]["mode"] == "dual_token"
    assert diagnostics_response.json()["auth"]["write_enabled"] is True
    assert diagnostics_response.json()["auth"]["readonly_enabled"] is True
    get_settings.cache_clear()


def test_diagnostics_runtime_counters_track_errors_and_auth_rejections(monkeypatch) -> None:
    monkeypatch.setenv("AB_API_TOKEN", "super-secret-token")
    monkeypatch.setenv("AB_READONLY_API_TOKEN", "readonly-secret")
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        client.get("/health")
        client.get("/api/v1/diagnostics")
        client.get("/api/v1/projects", headers={"Authorization": "Bearer readonly-secret"})
        client.post(
            "/api/v1/calculate",
            headers={"Authorization": "Bearer readonly-secret"},
            json={
                "metric_type": "binary",
                "baseline_value": 0.042,
                "mde_pct": 5,
                "alpha": 0.05,
                "power": 0.8,
                "expected_daily_traffic": 12000,
                "audience_share_in_test": 0.6,
                "traffic_split": [50, 50],
                "variants_count": 2,
            },
        )
        diagnostics_response = client.get(
            "/api/v1/diagnostics",
            headers={"Authorization": "Bearer super-secret-token"},
        )

    assert diagnostics_response.status_code == 200
    runtime = diagnostics_response.json()["runtime"]
    assert runtime["total_requests"] >= 4
    assert runtime["success_responses"] >= 2
    assert runtime["client_error_responses"] >= 1
    assert runtime["server_error_responses"] == 0
    assert runtime["auth_rejections"] >= 1
    assert runtime["last_error_code"] == "forbidden"
    assert runtime["last_error_at"] is not None
    assert runtime["last_request_at"] is not None
    get_settings.cache_clear()


def test_api_token_does_not_break_cors_preflight(monkeypatch) -> None:
    monkeypatch.setenv("AB_API_TOKEN", "super-secret-token")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.options(
            "/api/v1/calculate",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    get_settings.cache_clear()
