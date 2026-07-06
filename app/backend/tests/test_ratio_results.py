"""Tests for the post-hoc ratio analyzer (``analyze_ratio_results`` + ``POST /api/v1/results/ratio``).

The delta-method math itself is covered by ``test_ratio.py`` (including a bootstrap verification of
the variance); this file covers the new *input path* — raw per-user (numerator, denominator) pairs
reduced to sufficient statistics — against reference numbers frozen from an independent numpy/scipy
computation (``scratchpad/verify_ratio_posthoc.py``, run before implementation), plus the schema
guards and the HTTP contract.
"""

import pytest
from fastapi.testclient import TestClient

from app.backend.app.main import create_app
from app.backend.app.schemas.api import RatioArm, RatioResultsRequest
from app.backend.app.services.results_service import analyze_ratio_results

# Hand-pinned per-user pairs (a revenue-per-session-style metric); frozen against an independent
# numpy delta-method computation: control R = 0.4361702128, treatment R = 0.5380000000,
# effect = 0.1018297872, SE = 0.0116452917, z = 8.7442882237, CI (0.0790054349, 0.1246541396).
CONTROL_DEN = [3, 5, 2, 8, 4, 6, 3, 7, 5, 4, 2, 6, 5, 3, 9, 4, 5, 6, 3, 4]
CONTROL_NUM = [1.2, 2.1, 0.7, 3.9, 1.5, 2.8, 1.1, 3.2, 2.4, 1.6, 0.9, 2.5, 2.2, 1.0, 4.4, 1.8, 2.0, 2.7, 1.3, 1.7]
TREATMENT_DEN = [4, 6, 3, 7, 5, 5, 2, 8, 6, 4, 3, 7, 4, 5, 8, 3, 6, 5, 4, 5]
TREATMENT_NUM = [2.0, 3.1, 1.4, 3.8, 2.6, 2.9, 1.0, 4.5, 3.3, 2.1, 1.5, 3.9, 2.2, 2.7, 4.6, 1.6, 3.2, 2.8, 2.0, 2.6]

# Weak variant (treatment numerators shifted down by 0.09 per denominator unit): treatment
# R = 0.4480000000, effect = 0.0118297872, z = 1.0158429278, p = 0.3097041902 — not significant.
TREATMENT_NUM_WEAK = [y - 0.09 * x for x, y in zip(TREATMENT_DEN, TREATMENT_NUM, strict=True)]


def _request(treatment_num: list[float], alpha: float = 0.05) -> RatioResultsRequest:
    return RatioResultsRequest(
        control_arm=RatioArm(numerators=CONTROL_NUM, denominators=CONTROL_DEN),
        treatment_arm=RatioArm(numerators=treatment_num, denominators=TREATMENT_DEN),
        alpha=alpha,
    )


def _payload(treatment_num: list[float]) -> dict[str, object]:
    return {
        "control_arm": {"numerators": CONTROL_NUM, "denominators": CONTROL_DEN},
        "treatment_arm": {"numerators": treatment_num, "denominators": TREATMENT_DEN},
        "alpha": 0.05,
    }


def test_service_matches_frozen_numpy_reference() -> None:
    response = analyze_ratio_results(_request(TREATMENT_NUM))
    assert response.metric_type == "ratio"
    assert response.observed_effect == pytest.approx(0.101830, abs=1e-6)
    assert response.test_statistic == pytest.approx(8.7443, abs=1e-4)
    assert response.ci_lower == pytest.approx(0.079005, abs=1e-6)
    assert response.ci_upper == pytest.approx(0.124654, abs=1e-6)
    assert response.p_value == pytest.approx(0.0, abs=1e-6)
    assert response.is_significant is True
    # A ratio is not a percentage rate; the two-proportion fields stay empty.
    assert response.control_rate is None and response.treatment_rate is None


def test_service_weak_effect_not_significant() -> None:
    response = analyze_ratio_results(_request(TREATMENT_NUM_WEAK))
    assert response.observed_effect == pytest.approx(0.011830, abs=1e-6)
    assert response.test_statistic == pytest.approx(1.0158, abs=1e-4)
    assert response.p_value == pytest.approx(0.309704, abs=1e-6)
    assert response.is_significant is False


def test_service_agrees_with_live_ratio_path_by_construction() -> None:
    """Post-hoc and live ratio readouts share compare_ratios + build_ratio_results_response, so the
    same pairs fed through the post-hoc entry reproduce the live comparison's numbers exactly."""
    from app.backend.app.services.results_service import build_ratio_results_response
    from app.backend.app.stats.ratio import compare_ratios

    live = compare_ratios(
        {
            "n": len(CONTROL_DEN),
            "sum_x": sum(CONTROL_DEN),
            "sum_x2": sum(x * x for x in CONTROL_DEN),
            "sum_y": sum(CONTROL_NUM),
            "sum_y2": sum(y * y for y in CONTROL_NUM),
            "sum_xy": sum(x * y for x, y in zip(CONTROL_DEN, CONTROL_NUM, strict=True)),
        },
        {
            "n": len(TREATMENT_DEN),
            "sum_x": sum(TREATMENT_DEN),
            "sum_x2": sum(x * x for x in TREATMENT_DEN),
            "sum_y": sum(TREATMENT_NUM),
            "sum_y2": sum(y * y for y in TREATMENT_NUM),
            "sum_xy": sum(x * y for x, y in zip(TREATMENT_DEN, TREATMENT_NUM, strict=True)),
        },
        0.05,
    )
    assert live is not None
    assert analyze_ratio_results(_request(TREATMENT_NUM)) == build_ratio_results_response(live, 0.05)


def test_service_degenerate_zero_denominator_raises() -> None:
    request = RatioResultsRequest(
        control_arm=RatioArm(numerators=[1.0, 2.0, 3.0], denominators=[0.0, 0.0, 0.0]),
        treatment_arm=RatioArm(numerators=TREATMENT_NUM, denominators=TREATMENT_DEN),
    )
    with pytest.raises(ValueError):
        analyze_ratio_results(request)


def test_service_degenerate_zero_variance_raises() -> None:
    constant = RatioArm(numerators=[1.0, 1.0, 1.0], denominators=[2.0, 2.0, 2.0])
    with pytest.raises(ValueError):
        analyze_ratio_results(RatioResultsRequest(control_arm=constant, treatment_arm=constant))


def test_arm_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError):
        RatioArm(numerators=[1.0, 2.0, 3.0], denominators=[1.0, 2.0])


def test_arm_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError):
        RatioArm(numerators=[1.0, float("nan"), 3.0], denominators=[1.0, 2.0, 3.0])


def test_endpoint_ratio_round_trip() -> None:
    client = TestClient(create_app())
    response = client.post("/api/v1/results/ratio", json=_payload(TREATMENT_NUM))
    assert response.status_code == 200
    body = response.json()
    assert body["metric_type"] == "ratio"
    assert body["observed_effect"] == pytest.approx(0.101830, abs=1e-6)
    assert body["test_statistic"] == pytest.approx(8.7443, abs=1e-4)
    assert body["is_significant"] is True


def test_endpoint_localizes_via_accept_language() -> None:
    client = TestClient(create_app())
    english = client.post("/api/v1/results/ratio", json=_payload(TREATMENT_NUM))
    russian = client.post(
        "/api/v1/results/ratio", json=_payload(TREATMENT_NUM), headers={"Accept-Language": "ru"}
    )
    assert english.status_code == 200 and russian.status_code == 200
    en, ru = english.json(), russian.json()
    assert ru["verdict"] != en["verdict"]
    # Numbers are language-independent.
    assert ru["p_value"] == en["p_value"]
    assert ru["observed_effect"] == en["observed_effect"]


def test_endpoint_degenerate_returns_400() -> None:
    client = TestClient(create_app())
    payload = {
        "control_arm": {"numerators": [1.0, 1.0, 1.0], "denominators": [2.0, 2.0, 2.0]},
        "treatment_arm": {"numerators": [1.0, 1.0, 1.0], "denominators": [2.0, 2.0, 2.0]},
    }
    response = client.post("/api/v1/results/ratio", json=payload)
    assert response.status_code == 400


def test_endpoint_length_mismatch_returns_422() -> None:
    client = TestClient(create_app())
    payload = {
        "control_arm": {"numerators": [1.0, 2.0, 3.0], "denominators": [1.0, 2.0]},
        "treatment_arm": {"numerators": TREATMENT_NUM, "denominators": TREATMENT_DEN},
    }
    response = client.post("/api/v1/results/ratio", json=payload)
    assert response.status_code == 422


def test_endpoint_single_user_arm_returns_422() -> None:
    client = TestClient(create_app())
    payload = {
        "control_arm": {"numerators": [1.0], "denominators": [2.0]},
        "treatment_arm": {"numerators": TREATMENT_NUM, "denominators": TREATMENT_DEN},
    }
    response = client.post("/api/v1/results/ratio", json=payload)
    assert response.status_code == 422
