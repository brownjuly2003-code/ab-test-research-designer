"""Tests for the Cox proportional-hazards treatment-effect analyzer (``stats/cox_ph.py``) and its
service / endpoint wiring inside the survival section.

The fit is frozen against BOTH ``statsmodels 0.14.6`` ``PHReg(ties="efron")`` (agreement ≤1e-10) and
``lifelines 0.30.3`` ``CoxPHFitter`` (≤3e-7) in ``scratchpad/verify_cox_ph.py`` (neither is a runtime
dependency): on the Freireich data with x = 1 for 6-MP, β = −1.5721251488, SE = 0.4123967177,
HR = 0.207604 with 95% CI (0.092513, 0.465873), Wald z = −3.812167, p = 0.0001377538. Also covered:
the degenerate guards (all censored; monotone likelihood where every event sits in one arm), the
structural guards (validation, observation cap), the service response shape (Wald χ² in
``chi_square``, HR effect-size fields, log-rank descriptive expected counts) and the HTTP layer
(round-trip, RU localization, Cox-with-additional-arms → 422, degenerate → 400).
"""

import pytest
from fastapi.testclient import TestClient

from app.backend.app.main import create_app
from app.backend.app.schemas.api import SurvivalArm, SurvivalResultsRequest
from app.backend.app.services.results_service import analyze_survival_results
from app.backend.app.stats.cox_ph import cox_ph_treatment_effect
from app.backend.app.stats.survival import MAX_SURVIVAL_TOTAL

# Freireich et al. (1963), same arms the survival tests pin (control = placebo, treatment = 6-MP).
PLACEBO_DURATIONS = [1.0, 1, 2, 2, 3, 4, 4, 5, 5, 8, 8, 8, 8, 11, 11, 12, 12, 15, 17, 22, 23]
PLACEBO_EVENTS = [True] * 21
MP6_RAW = [
    (6, True), (6, True), (6, True), (6, False), (7, True), (9, False), (10, True), (10, False),
    (11, False), (13, True), (16, True), (17, False), (19, False), (20, False), (22, True),
    (23, True), (25, False), (32, False), (32, False), (34, False), (35, False),
]
MP6_DURATIONS = [float(t) for t, _ in MP6_RAW]
MP6_EVENTS = [e for _, e in MP6_RAW]


def _freireich_fit() -> dict:
    result = cox_ph_treatment_effect(
        PLACEBO_DURATIONS, PLACEBO_EVENTS, MP6_DURATIONS, MP6_EVENTS
    )
    assert result is not None
    return result


def test_matches_frozen_statsmodels_and_lifelines_reference() -> None:
    result = _freireich_fit()
    assert result["log_hazard_ratio"] == pytest.approx(-1.5721251488, abs=1e-9)
    assert result["standard_error"] == pytest.approx(0.4123967177, abs=1e-9)
    assert result["hazard_ratio"] == pytest.approx(0.207604, abs=1e-6)
    assert result["hr_ci_lower"] == pytest.approx(0.092513, abs=1e-6)
    assert result["hr_ci_upper"] == pytest.approx(0.465873, abs=1e-6)
    assert result["z_statistic"] == pytest.approx(-3.812167, abs=1e-6)
    assert result["p_value"] == pytest.approx(0.0001377538, abs=1e-9)
    assert result["is_significant"] is True


def test_arm_swap_inverts_the_hazard_ratio() -> None:
    """Swapping control and treatment flips the sign of β, so the HR inverts — the fit is a directed
    effect (treatment vs control), unlike the symmetric log-rank χ²."""
    forward = _freireich_fit()
    reversed_ = cox_ph_treatment_effect(
        MP6_DURATIONS, MP6_EVENTS, PLACEBO_DURATIONS, PLACEBO_EVENTS
    )
    assert reversed_ is not None
    assert reversed_["log_hazard_ratio"] == pytest.approx(
        -forward["log_hazard_ratio"], abs=1e-8
    )
    assert reversed_["hazard_ratio"] == pytest.approx(1.0 / forward["hazard_ratio"], rel=1e-6)


def test_all_censored_returns_none() -> None:
    assert (
        cox_ph_treatment_effect([1.0, 2.0], [False, False], [1.5, 2.5], [False, False]) is None
    )


def test_monotone_likelihood_returns_none() -> None:
    # Every event in the control arm while the treatment arm outlives them all: β̂ → −∞.
    assert (
        cox_ph_treatment_effect(
            [1.0, 2.0, 3.0], [True, True, True], [10.0, 11.0, 12.0], [False, False, False]
        )
        is None
    )


def test_rejects_structurally_invalid_arms() -> None:
    with pytest.raises(ValueError):
        cox_ph_treatment_effect([1.0, -2.0], [True, True], [1.0], [True])


def test_rejects_over_cap() -> None:
    half = MAX_SURVIVAL_TOTAL // 2 + 1
    with pytest.raises(ValueError, match="cap"):
        cox_ph_treatment_effect([1.0] * half, [True] * half, [1.0] * half, [True] * half)


def test_p_value_in_unit_interval_and_ci_brackets_hr() -> None:
    result = _freireich_fit()
    assert 0.0 <= result["p_value"] <= 1.0
    assert result["hr_ci_lower"] < result["hazard_ratio"] < result["hr_ci_upper"]


# --- service layer -------------------------------------------------------------------------------


def _cox_request() -> SurvivalResultsRequest:
    return SurvivalResultsRequest(
        control_arm=SurvivalArm(durations=PLACEBO_DURATIONS, events_observed=PLACEBO_EVENTS),
        treatment_arm=SurvivalArm(durations=MP6_DURATIONS, events_observed=MP6_EVENTS),
        test_type="cox",
    )


def test_service_populates_hazard_ratio_fields() -> None:
    response = analyze_survival_results(_cox_request())
    assert response.test_type == "cox"
    assert response.hazard_ratio == pytest.approx(0.2076, abs=1e-4)
    assert response.hazard_ratio_ci_lower == pytest.approx(0.0925, abs=1e-4)
    assert response.hazard_ratio_ci_upper == pytest.approx(0.4659, abs=1e-4)
    assert response.log_hazard_ratio == pytest.approx(-1.572125, abs=1e-6)
    assert response.log_hazard_ratio_se == pytest.approx(0.412397, abs=1e-6)
    # chi_square carries the Wald z² on 1 df for the Cox branch.
    assert response.chi_square == pytest.approx(14.5326, abs=1e-4)
    assert response.degrees_of_freedom == 1
    assert response.p_value == pytest.approx(0.000138, abs=1e-6)
    assert response.fh_rho is None and response.fh_gamma is None


def test_service_cox_keeps_descriptive_log_rank_expected_counts() -> None:
    """The per-arm expected counts are the test-agnostic risk-set expectations (same numbers the
    log-rank branch reports for the same data), so the readout stays comparable across branches."""
    response = analyze_survival_results(_cox_request())
    assert len(response.arm_summaries) == 2
    assert response.observed_control == 21
    assert response.expected_control == pytest.approx(10.7495, abs=1e-3)
    assert response.observed_treatment == 9
    assert response.expected_treatment == pytest.approx(19.2505, abs=1e-3)
    # Kaplan-Meier curves render exactly as on the log-rank branch.
    assert len(response.treatment_curve) == 7
    assert response.additional_arm_curves == []


def test_service_cox_degenerate_raises() -> None:
    request = SurvivalResultsRequest(
        control_arm=SurvivalArm(durations=[1.0, 2.0], events_observed=[False, False]),
        treatment_arm=SurvivalArm(durations=[1.0, 2.0], events_observed=[False, False]),
        test_type="cox",
    )
    with pytest.raises(ValueError):
        analyze_survival_results(request)


def test_schema_rejects_cox_with_additional_arms() -> None:
    with pytest.raises(ValueError):
        SurvivalResultsRequest(
            control_arm=SurvivalArm(durations=[1.0, 2.0], events_observed=[True, True]),
            treatment_arm=SurvivalArm(durations=[1.0, 2.0], events_observed=[True, True]),
            additional_arms=[SurvivalArm(durations=[1.0, 2.0], events_observed=[True, True])],
            test_type="cox",
        )


# --- HTTP endpoint -------------------------------------------------------------------------------


def _cox_payload() -> dict:
    return {
        "control_arm": {"durations": PLACEBO_DURATIONS, "events_observed": PLACEBO_EVENTS},
        "treatment_arm": {"durations": MP6_DURATIONS, "events_observed": MP6_EVENTS},
        "test_type": "cox",
    }


def test_endpoint_cox_round_trip() -> None:
    client = TestClient(create_app())
    response = client.post("/api/v1/results/survival", json=_cox_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["test_type"] == "cox"
    assert body["hazard_ratio"] == pytest.approx(0.2076, abs=1e-4)
    assert body["hazard_ratio_ci_lower"] == pytest.approx(0.0925, abs=1e-4)
    assert body["hazard_ratio_ci_upper"] == pytest.approx(0.4659, abs=1e-4)
    assert body["chi_square"] == pytest.approx(14.5326, abs=1e-4)
    assert body["is_significant"] is True
    assert "hazard ratio" in body["interpretation"].lower()


def test_endpoint_cox_localizes_via_accept_language() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/results/survival", json=_cox_payload(), headers={"Accept-Language": "ru"}
    )
    assert response.status_code == 200
    assert "Кокса" in response.json()["interpretation"]


def test_endpoint_cox_with_additional_arms_returns_422() -> None:
    client = TestClient(create_app())
    payload = _cox_payload()
    payload["additional_arms"] = [{"durations": [1.0, 2.0], "events_observed": [True, True]}]
    response = client.post("/api/v1/results/survival", json=payload)
    assert response.status_code == 422


def test_endpoint_cox_monotone_likelihood_returns_400() -> None:
    client = TestClient(create_app())
    payload = {
        "control_arm": {"durations": [1.0, 2.0, 3.0], "events_observed": [True, True, True]},
        "treatment_arm": {
            "durations": [10.0, 11.0, 12.0],
            "events_observed": [False, False, False],
        },
        "test_type": "cox",
    }
    response = client.post("/api/v1/results/survival", json=payload)
    assert response.status_code == 400
