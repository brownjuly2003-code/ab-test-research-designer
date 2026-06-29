from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.main import create_app


def _project_payload(name: str) -> dict:
    return {
        "project": {
            "project_name": name,
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
        "additional_context": {
            "llm_context": "",
        },
    }


def test_results_endpoint_binary_significant() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "binary",
            "binary": {
                "control_conversions": 1750,
                "control_users": 50000,
                "treatment_conversions": 2000,
                "treatment_users": 50000,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_significant"] is True
    assert payload["p_value"] < 0.05
    assert payload["observed_effect"] == pytest.approx(0.5, abs=0.01)


def test_results_endpoint_binary_interpretation_reflects_custom_alpha() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "binary",
            "binary": {
                "control_conversions": 1750,
                "control_users": 50000,
                "treatment_conversions": 2000,
                "treatment_users": 50000,
                "alpha": 0.01,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ci_level"] == pytest.approx(0.99)
    assert "99.0% CI" in payload["interpretation"]
    assert "95.0% CI" not in payload["interpretation"]


def test_results_endpoint_localizes_verdict_via_accept_language() -> None:
    client = TestClient(create_app())
    body = {
        "metric_type": "binary",
        "binary": {
            "control_conversions": 100,
            "control_users": 1000,
            "treatment_conversions": 130,
            "treatment_users": 1000,
        },
    }

    english = client.post("/api/v1/results", json=body)
    russian = client.post("/api/v1/results", json=body, headers={"Accept-Language": "ru"})

    assert english.status_code == 200 and russian.status_code == 200
    en_payload = english.json()
    ru_payload = russian.json()

    # English stays byte-identical to the historical wording.
    assert en_payload["verdict"] == "Statistically significant uplift at alpha=0.050"
    # Russian is localized but conveys the same significant-uplift verdict.
    assert ru_payload["verdict"] != en_payload["verdict"]
    assert "alpha=0.050" in ru_payload["verdict"]
    assert "значим" in ru_payload["verdict"]
    # Numbers are language-independent.
    assert ru_payload["test_statistic"] == en_payload["test_statistic"]
    assert ru_payload["p_value"] == en_payload["p_value"]
    assert ru_payload["ci_lower"] == en_payload["ci_lower"]
    assert ru_payload["ci_upper"] == en_payload["ci_upper"]


def test_results_endpoint_binary_not_significant_and_ci_crosses_zero() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "binary",
            "binary": {
                "control_conversions": 100,
                "control_users": 1000,
                "treatment_conversions": 105,
                "treatment_users": 1000,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_significant"] is False
    assert payload["ci_lower"] <= 0 <= payload["ci_upper"]


def test_results_endpoint_continuous_significant() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "continuous",
            "continuous": {
                "control_mean": 45.0,
                "control_std": 12.0,
                "control_n": 5000,
                "treatment_mean": 47.5,
                "treatment_std": 12.5,
                "treatment_n": 5000,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_significant"] is True
    assert payload["observed_effect"] == pytest.approx(2.5, abs=0.01)


def test_results_endpoint_continuous_uses_student_t_for_small_samples() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "continuous",
            "continuous": {
                "control_mean": 10.0,
                "control_std": 2.0,
                "control_n": 10,
                "treatment_mean": 11.5,
                "treatment_std": 2.0,
                "treatment_n": 10,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["test_statistic"] == pytest.approx(1.6771, abs=0.001)
    assert payload["p_value"] == pytest.approx(0.110812, abs=1e-4)
    assert payload["is_significant"] is False

    ci_half = (payload["ci_upper"] - payload["ci_lower"]) / 2
    assert ci_half == pytest.approx(1.879122, abs=1e-3)

    assert payload["p_value"] > 0.10
    assert ci_half > 1.80

    assert payload["power_achieved"] == pytest.approx(0.339, abs=0.01)


def test_results_endpoint_continuous_converges_to_normal_for_large_samples() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "continuous",
            "continuous": {
                "control_mean": 100.0,
                "control_std": 15.0,
                "control_n": 50000,
                "treatment_mean": 100.5,
                "treatment_std": 15.0,
                "treatment_n": 50000,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_significant"] is True
    assert payload["p_value"] < 1e-5


def test_project_update_can_persist_saved_observed_results() -> None:
    client = TestClient(create_app())
    create_response = client.post("/api/v1/projects", json=_project_payload("Observed results"))

    assert create_response.status_code == 200
    project_id = create_response.json()["id"]

    results_request = {
        "metric_type": "binary",
        "binary": {
            "control_conversions": 1750,
            "control_users": 50000,
            "treatment_conversions": 2000,
            "treatment_users": 50000,
        },
    }
    results_response = client.post("/api/v1/results", json=results_request)

    assert results_response.status_code == 200

    updated_payload = _project_payload("Observed results")
    updated_payload["additional_context"]["observed_results"] = {
        "request": results_request,
        "analysis": results_response.json(),
    }

    update_response = client.put(f"/api/v1/projects/{project_id}", json=updated_payload)

    assert update_response.status_code == 200
    assert update_response.json()["payload"]["additional_context"]["observed_results"]["analysis"]["is_significant"] is True

    get_response = client.get(f"/api/v1/projects/{project_id}")

    assert get_response.status_code == 200
    assert get_response.json()["payload"]["additional_context"]["observed_results"]["request"]["metric_type"] == "binary"


# --- Mann–Whitney (non-parametric, raw-sample) endpoint --------------------------------------


def test_results_endpoint_mann_whitney_significant() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "mann_whitney",
            "ranked": {
                "control_values": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                "treatment_values": [6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metric_type"] == "mann_whitney"
    assert payload["is_significant"] is True
    # Hodges–Lehmann shift of a clean +5 location difference, CI excludes zero.
    assert payload["observed_effect"] == pytest.approx(5.0, abs=0.5)
    assert payload["ci_lower"] > 0
    # Rank-biserial effect size is surfaced with its localized label.
    assert payload["effect_size"] is not None
    assert payload["effect_size_label"]
    assert "Mann" in payload["interpretation"]


def test_results_endpoint_mann_whitney_not_significant_ci_crosses_zero() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "mann_whitney",
            "ranked": {
                "control_values": [4, 5, 6, 5, 4, 6, 5, 4, 6, 5],
                "treatment_values": [5, 4, 6, 5, 6, 4, 5, 6, 4, 5],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_significant"] is False
    assert payload["ci_lower"] <= 0 <= payload["ci_upper"]


def test_results_endpoint_mann_whitney_localizes_via_accept_language() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        headers={"Accept-Language": "ru"},
        json={
            "metric_type": "mann_whitney",
            "ranked": {
                "control_values": [1, 2, 3, 4, 5],
                "treatment_values": [7, 8, 9, 10, 11],
            },
        },
    )

    assert response.status_code == 200
    # Russian interpretation keeps the technical term but localizes the prose.
    assert "Медиана" in response.json()["interpretation"]


def test_results_endpoint_mann_whitney_requires_ranked_data() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "mann_whitney",
            "continuous": {
                "control_mean": 1.0,
                "control_std": 1.0,
                "control_n": 10,
                "treatment_mean": 2.0,
                "treatment_std": 1.0,
                "treatment_n": 10,
            },
        },
    )

    assert response.status_code == 422


def test_results_endpoint_mann_whitney_rejects_oversized_sample() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "mann_whitney",
            "ranked": {
                "control_values": [float(i) for i in range(1001)],
                "treatment_values": [1.0, 2.0],
            },
        },
    )

    assert response.status_code == 422


def test_results_endpoint_fisher_exact_significant() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "fisher_exact",
            "binary": {
                "control_conversions": 8,
                "control_users": 10,
                "treatment_conversions": 1,
                "treatment_users": 6,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metric_type"] == "fisher_exact"
    assert payload["is_significant"] is True
    # Exact two-sided p-value for [[8,2],[1,5]] (== scipy) and the sample odds ratio surfaced.
    assert payload["p_value"] == pytest.approx(0.034965, abs=1e-5)
    assert payload["effect_size"] == pytest.approx(20.0)
    assert payload["effect_size_label"]
    assert "Fisher" in payload["interpretation"]


def test_results_endpoint_fisher_exact_localizes_via_accept_language() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        headers={"Accept-Language": "ru"},
        json={
            "metric_type": "fisher_exact",
            "binary": {
                "control_conversions": 8,
                "control_users": 10,
                "treatment_conversions": 1,
                "treatment_users": 6,
            },
        },
    )

    assert response.status_code == 200
    # Russian interpretation keeps the technical term but localizes the prose.
    assert "Фишера" in response.json()["interpretation"]


def test_results_endpoint_fisher_exact_undefined_odds_ratio_still_ok() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "fisher_exact",
            "binary": {
                "control_conversions": 10,
                "control_users": 10,
                "treatment_conversions": 3,
                "treatment_users": 8,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    # A zero off-diagonal cell makes the odds ratio undefined, but the exact p-value is defined.
    assert payload["effect_size"] is None
    assert 0.0 <= payload["p_value"] <= 1.0


def test_results_endpoint_fisher_exact_requires_binary_data() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "fisher_exact",
            "ranked": {
                "control_values": [1, 2, 3],
                "treatment_values": [4, 5, 6],
            },
        },
    )

    assert response.status_code == 422


def test_results_endpoint_fisher_exact_rejects_oversized_table() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "fisher_exact",
            "binary": {
                "control_conversions": 150_000,
                "control_users": 300_000,
                "treatment_conversions": 160_000,
                "treatment_users": 300_000,
            },
        },
    )

    # Exact enumeration is capped: the table exceeds MAX_FISHER_EXACT_TOTAL and is rejected with a
    # clear message (a service-level ValueError -> 400) directing the caller to the binary test.
    assert response.status_code == 400
