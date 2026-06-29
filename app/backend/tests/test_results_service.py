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


def test_results_endpoint_mann_whitney_exact_for_small_tie_free_sample() -> None:
    client = TestClient(create_app())

    # Small, tie-free (disjoint) arms -> the exact p-value path; the interpretation names the method.
    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "mann_whitney",
            "ranked": {
                "control_values": [1, 2, 3, 4],
                "treatment_values": [5, 6, 7, 8],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_significant"] is True
    # Exact two-sided p for complete separation of 4 vs 4 is 2 / C(8,4) = 2/70.
    assert payload["p_value"] == pytest.approx(2 / 70, abs=1e-6)
    assert "(exact)" in payload["interpretation"]


def test_results_endpoint_mann_whitney_asymptotic_when_ties_present() -> None:
    client = TestClient(create_app())

    # Overlapping arms share values -> ties -> the corrected normal approximation, named as such.
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
    assert "(normal approximation)" in response.json()["interpretation"]


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


def test_results_endpoint_bootstrap_significant() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "bootstrap",
            "ranked": {
                "control_values": [float(i) for i in range(30)],
                "treatment_values": [float(i) + 6.0 for i in range(30)],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metric_type"] == "bootstrap"
    assert payload["is_significant"] is True
    # Mean difference of a clean +6 location shift; the percentile bootstrap CI excludes zero.
    assert payload["observed_effect"] == pytest.approx(6.0, abs=0.5)
    assert payload["ci_lower"] > 0
    # Cohen's d effect size is surfaced with its localized label.
    assert payload["effect_size"] is not None
    assert payload["effect_size_label"]
    assert "bootstrap" in payload["interpretation"].lower()


def test_results_endpoint_bootstrap_not_significant_ci_crosses_zero() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "bootstrap",
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


def test_results_endpoint_bootstrap_localizes_via_accept_language() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        headers={"Accept-Language": "ru"},
        json={
            "metric_type": "bootstrap",
            "ranked": {
                "control_values": [1, 2, 3, 4, 5],
                "treatment_values": [7, 8, 9, 10, 11],
            },
        },
    )

    assert response.status_code == 200
    # Russian interpretation localizes the prose (the mean-difference phrasing).
    assert "средних" in response.json()["interpretation"]


def test_results_endpoint_bootstrap_requires_ranked_data() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "bootstrap",
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


def test_results_endpoint_quantile_significant() -> None:
    client = TestClient(create_app())

    # Two tight clusters a constant apart: the median shift is unambiguous.
    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "quantile",
            "ranked": {
                "control_values": [1.0] * 15 + [2.0] * 15,
                "treatment_values": [11.0] * 15 + [12.0] * 15,
                "quantile": 0.5,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metric_type"] == "quantile"
    assert payload["is_significant"] is True
    assert payload["observed_effect"] == pytest.approx(10.0, abs=0.5)
    assert payload["ci_lower"] > 0
    # The chosen quantile is surfaced in the localized interpretation as a percentile.
    assert "P50" in payload["interpretation"]
    assert "quantile" in payload["interpretation"].lower()


def test_results_endpoint_quantile_p90_targets_upper_tail() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "quantile",
            "ranked": {
                "control_values": [float(i) for i in range(1, 101)],
                "treatment_values": [float(i) + 10.0 for i in range(1, 101)],
                "quantile": 0.9,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metric_type"] == "quantile"
    assert payload["observed_effect"] == pytest.approx(10.0, abs=1.0)
    assert "P90" in payload["interpretation"]


def test_results_endpoint_quantile_not_significant_ci_crosses_zero() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "quantile",
            "ranked": {
                "control_values": [4, 5, 6, 5, 4, 6, 5, 4, 6, 5],
                "treatment_values": [5, 4, 6, 5, 6, 4, 5, 6, 4, 5],
                "quantile": 0.5,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_significant"] is False
    assert payload["ci_lower"] <= 0 <= payload["ci_upper"]


def test_results_endpoint_quantile_defaults_to_median() -> None:
    client = TestClient(create_app())

    # With the quantile omitted the schema default (0.5 = median) applies.
    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "quantile",
            "ranked": {
                "control_values": [1.0, 2.0, 3.0, 4.0],
                "treatment_values": [5.0, 6.0, 7.0, 8.0],
            },
        },
    )

    assert response.status_code == 200
    assert "P50" in response.json()["interpretation"]


def test_results_endpoint_quantile_localizes_via_accept_language() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        headers={"Accept-Language": "ru"},
        json={
            "metric_type": "quantile",
            "ranked": {
                "control_values": [1, 2, 3, 4, 5],
                "treatment_values": [7, 8, 9, 10, 11],
                "quantile": 0.5,
            },
        },
    )

    assert response.status_code == 200
    # Russian interpretation localizes the prose (the quantile phrasing).
    assert "квантил" in response.json()["interpretation"]


def test_results_endpoint_quantile_requires_ranked_data() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "quantile",
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


def test_results_endpoint_quantile_rejects_out_of_range_quantile() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "quantile",
            "ranked": {
                "control_values": [1.0, 2.0, 3.0],
                "treatment_values": [4.0, 5.0, 6.0],
                "quantile": 1.5,
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


def test_results_endpoint_count_significant() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "count",
            "count": {
                "control_events": 10,
                "control_exposure": 100,
                "treatment_events": 25,
                "treatment_exposure": 100,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metric_type"] == "count"
    assert payload["is_significant"] is True
    # Conditional binomial exact p for (10 vs 25, equal exposure) and the rate ratio surfaced.
    assert payload["p_value"] == pytest.approx(0.016674, abs=1e-5)
    assert payload["effect_size"] == pytest.approx(2.5)
    assert payload["effect_size_label"]
    assert "Poisson" in payload["interpretation"]


def test_results_endpoint_count_localizes_via_accept_language() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        headers={"Accept-Language": "ru"},
        json={
            "metric_type": "count",
            "count": {
                "control_events": 10,
                "control_exposure": 100,
                "treatment_events": 25,
                "treatment_exposure": 100,
            },
        },
    )

    assert response.status_code == 200
    assert "Пуассона" in response.json()["interpretation"]


def test_results_endpoint_count_degenerate_when_no_events() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "count",
            "count": {
                "control_events": 0,
                "control_exposure": 100,
                "treatment_events": 0,
                "treatment_exposure": 100,
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["is_significant"] is False


def test_results_endpoint_count_requires_count_data() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "count",
            "binary": {
                "control_conversions": 1,
                "control_users": 10,
                "treatment_conversions": 2,
                "treatment_users": 10,
            },
        },
    )

    assert response.status_code == 422


def test_results_endpoint_equivalence_demonstrated() -> None:
    client = TestClient(create_app())

    # Means 0.1 apart with tight, well-powered arms inside a margin of 0.5: equivalence is concluded.
    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "equivalence",
            "continuous": {
                "control_mean": 0.0,
                "control_std": 1.0,
                "control_n": 100,
                "treatment_mean": 0.1,
                "treatment_std": 1.0,
                "treatment_n": 100,
                "equivalence_margin": 0.5,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metric_type"] == "equivalence"
    assert payload["is_significant"] is True  # "significant" == equivalence demonstrated here
    assert payload["observed_effect"] == pytest.approx(0.1, abs=1e-6)
    # The reported interval is the 90% (1 - 2*alpha) TOST decision interval, fully inside ±0.5.
    assert payload["ci_level"] == pytest.approx(0.90, abs=1e-9)
    assert -0.5 < payload["ci_lower"] and payload["ci_upper"] < 0.5
    assert "equivalence" in payload["interpretation"].lower()


def test_results_endpoint_equivalence_not_demonstrated_when_effect_exceeds_margin() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "equivalence",
            "continuous": {
                "control_mean": 10.0,
                "control_std": 2.0,
                "control_n": 50,
                "treatment_mean": 12.0,
                "treatment_std": 2.1,
                "treatment_n": 50,
                "equivalence_margin": 1.0,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metric_type"] == "equivalence"
    assert payload["is_significant"] is False
    assert payload["p_value"] == pytest.approx(0.991719, abs=1e-5)


def test_results_endpoint_equivalence_localizes_via_accept_language() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        headers={"Accept-Language": "ru"},
        json={
            "metric_type": "equivalence",
            "continuous": {
                "control_mean": 0.0,
                "control_std": 1.0,
                "control_n": 80,
                "treatment_mean": 0.05,
                "treatment_std": 1.0,
                "treatment_n": 80,
                "equivalence_margin": 0.5,
            },
        },
    )

    assert response.status_code == 200
    assert "эквивалентность" in response.json()["interpretation"].lower()


def test_results_endpoint_equivalence_requires_margin() -> None:
    client = TestClient(create_app())

    # The equivalence margin is mandatory for the TOST analysis.
    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "equivalence",
            "continuous": {
                "control_mean": 0.0,
                "control_std": 1.0,
                "control_n": 10,
                "treatment_mean": 0.1,
                "treatment_std": 1.0,
                "treatment_n": 10,
            },
        },
    )

    assert response.status_code == 422


def test_results_endpoint_equivalence_requires_continuous_data() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/results",
        json={
            "metric_type": "equivalence",
            "ranked": {
                "control_values": [1.0, 2.0, 3.0],
                "treatment_values": [4.0, 5.0, 6.0],
            },
        },
    )

    assert response.status_code == 422
