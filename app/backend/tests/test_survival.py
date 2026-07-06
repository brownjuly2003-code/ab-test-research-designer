"""Tests for the survival analyzers (``stats/survival.py``) and their service / endpoint wiring.

Coverage: the Kaplan–Meier product-limit estimate and Greenwood standard errors, and the two-arm
log-rank (Mantel–Cox) chi-square / p-value, frozen against the canonical **Freireich et al. (1963)**
6-MP-vs-placebo leukemia dataset (published log-rank χ² ≈ 16.79, p ≈ 4.2e-5; the 6-MP Kaplan–Meier
survival estimates match Klein & Moeschberger). The frozen numbers were reproduced from-scratch and
cross-checked with ``scipy.stats.chi2.sf`` in ``scratchpad/verify_logrank_km.py`` (scipy is not a
runtime dependency, so the constants are pinned here to keep the suite stdlib-only and CI-safe). Also
covered: a tiny hand-computable example that pins the censoring / risk-set logic, the degenerate
all-censored guard (V = 0 → ``None`` → service ``ValueError`` → HTTP 400), the schema validation
(mismatched-length arrays / empty arms → 422), the observation cap, and the service + HTTP layer
(rounding, localization, per-arm survival curves in the 200 response).

The weighted k-sample generalization (``weighted_k_sample_log_rank_test``) is frozen against
``lifelines 0.30.3`` ``multivariate_logrank_test`` — cross-checked for the 2-arm G^ρ subfamily with
``statsmodels 0.14.6`` ``survdiff(weight_type="fh")`` — in
``scratchpad/verify_ksample_weighted_logrank.py`` (neither is a runtime dependency): 3-arm unweighted
χ² = 19.389263 (df 2), 2-arm FH(1,0) = 14.457151, FH(0,1) = 13.048449, 3-arm FH(1,0) = 16.701169.
The k = 2 unweighted case is pinned to agree with the legacy ``log_rank_test`` to 1e-12.
"""

import pytest
from fastapi.testclient import TestClient

from app.backend.app.main import create_app
from app.backend.app.schemas.api import SurvivalArm, SurvivalResultsRequest
from app.backend.app.services.results_service import analyze_survival_results
from app.backend.app.stats.survival import (
    MAX_SURVIVAL_TOTAL,
    kaplan_meier_estimate,
    log_rank_test,
    weighted_k_sample_log_rank_test,
)

# --- Freireich et al. (1963) leukemia remission data (arm 1 = 6-MP treatment, arm 2 = placebo) ------
# 6-MP: an event flag of False is a censored observation (still in remission at last follow-up).
PLACEBO_DURATIONS = [1, 1, 2, 2, 3, 4, 4, 5, 5, 8, 8, 8, 8, 11, 11, 12, 12, 15, 17, 22, 23]
PLACEBO_EVENTS = [True] * 21  # every placebo patient relapsed (no censoring)
MP6_RAW = [
    (6, True), (6, True), (6, True), (6, False), (7, True), (9, False), (10, True), (10, False),
    (11, False), (13, True), (16, True), (17, False), (19, False), (20, False), (22, True),
    (23, True), (25, False), (32, False), (32, False), (34, False), (35, False),
]
MP6_DURATIONS = [float(t) for t, _ in MP6_RAW]
MP6_EVENTS = [e for _, e in MP6_RAW]

# A hand-pinned third arm ("half-dose"): intermediate survival, some censoring. Used by the k-sample
# tests; the frozen chi-squares below come from lifelines' multivariate_logrank_test on these arms.
THIRD_RAW = [
    (2, True), (4, True), (5, False), (6, True), (7, True), (9, True), (11, False), (12, True),
    (14, True), (15, False), (18, True), (21, False), (24, True), (26, False), (30, False),
]
THIRD_DURATIONS = [float(t) for t, _ in THIRD_RAW]
THIRD_EVENTS = [e for _, e in THIRD_RAW]


# --- Kaplan–Meier estimator --------------------------------------------------------------------


def test_kaplan_meier_matches_klein_moeschberger_6mp_arm() -> None:
    points = kaplan_meier_estimate(MP6_DURATIONS, MP6_EVENTS)
    # One step point per distinct event time (censoring times do not create steps).
    times = [p["time"] for p in points]
    assert times == [6.0, 7.0, 10.0, 13.0, 16.0, 22.0, 23.0]
    survival = {p["time"]: p["survival"] for p in points}
    # Published 6-MP Kaplan–Meier survival (Klein & Moeschberger, "Survival Analysis").
    assert survival[6.0] == pytest.approx(0.857143, abs=1e-6)
    assert survival[7.0] == pytest.approx(0.806723, abs=1e-6)
    assert survival[10.0] == pytest.approx(0.752941, abs=1e-6)
    assert survival[13.0] == pytest.approx(0.690196, abs=1e-6)
    assert survival[16.0] == pytest.approx(0.627451, abs=1e-6)
    assert survival[22.0] == pytest.approx(0.537815, abs=1e-6)
    assert survival[23.0] == pytest.approx(0.448179, abs=1e-6)
    first = points[0]
    assert first["at_risk"] == 21
    assert first["n_events"] == 3
    # Greenwood standard error at t = 6 (matches the published value).
    assert first["std_error"] == pytest.approx(0.076360, abs=1e-6)
    assert first["ci_lower"] == pytest.approx(0.7075, abs=1e-3)
    assert first["ci_upper"] == pytest.approx(1.0, abs=1e-3)  # clamped to 1


def test_kaplan_meier_placebo_arm_has_no_censoring() -> None:
    points = kaplan_meier_estimate(PLACEBO_DURATIONS, PLACEBO_EVENTS)
    assert points[0]["at_risk"] == 21
    # Final placebo survival collapses toward 0 (everyone relapses); last step is the max time.
    assert points[-1]["time"] == 23.0
    assert points[-1]["survival"] == pytest.approx(0.0, abs=1e-9)


def test_kaplan_meier_fully_censored_arm_has_no_steps() -> None:
    assert kaplan_meier_estimate([1.0, 2.0, 3.0], [False, False, False]) == []


def test_kaplan_meier_survival_hits_zero_collapses_ci() -> None:
    # Every at-risk subject has the event at the last time: S(t) = 0, Greenwood variance undefined.
    points = kaplan_meier_estimate([1.0, 2.0, 2.0], [True, True, True])
    last = points[-1]
    assert last["survival"] == pytest.approx(0.0, abs=1e-12)
    assert last["std_error"] == 0.0
    assert last["ci_lower"] == 0.0
    assert last["ci_upper"] == 0.0


def test_kaplan_meier_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError):
        kaplan_meier_estimate([1.0, 2.0], [True])


def test_kaplan_meier_rejects_negative_durations() -> None:
    with pytest.raises(ValueError):
        kaplan_meier_estimate([-1.0, 2.0], [True, True])


# --- log-rank (Mantel–Cox) test ----------------------------------------------------------------


def test_log_rank_matches_freireich_published_chi_square() -> None:
    result = log_rank_test(MP6_DURATIONS, MP6_EVENTS, PLACEBO_DURATIONS, PLACEBO_EVENTS)
    assert result is not None
    # Frozen from scratchpad/verify_logrank_km.py, cross-checked with scipy.stats.chi2.sf(x, 1).
    assert result["chi_square"] == pytest.approx(16.7929409892, abs=1e-9)
    assert result["p_value"] == pytest.approx(4.168809e-05, abs=1e-9)
    assert result["observed1"] == 9
    assert result["expected1"] == pytest.approx(19.2505009480, abs=1e-9)
    assert result["observed2"] == 21
    assert result["expected2"] == pytest.approx(10.7494990520, abs=1e-9)
    assert result["variance"] == pytest.approx(6.2569605737, abs=1e-9)
    assert result["df"] == 1
    assert result["is_significant"] is True


def test_log_rank_is_symmetric_in_arm_order() -> None:
    forward = log_rank_test(MP6_DURATIONS, MP6_EVENTS, PLACEBO_DURATIONS, PLACEBO_EVENTS)
    reversed_ = log_rank_test(PLACEBO_DURATIONS, PLACEBO_EVENTS, MP6_DURATIONS, MP6_EVENTS)
    assert forward is not None and reversed_ is not None
    assert forward["chi_square"] == pytest.approx(reversed_["chi_square"], abs=1e-12)


def test_log_rank_small_hand_computable_example() -> None:
    # Arm1 [(1,event),(3,censored),(5,event)] vs arm2 [(2,event),(4,censored),(6,event)].
    result = log_rank_test([1.0, 3.0, 5.0], [True, False, True], [2.0, 4.0, 6.0], [True, False, True])
    assert result is not None
    assert result["observed1"] == 2
    assert result["expected1"] == pytest.approx(1.4, abs=1e-9)
    assert result["variance"] == pytest.approx(0.74, abs=1e-9)
    assert result["chi_square"] == pytest.approx(0.4864864865, abs=1e-9)
    assert result["p_value"] == pytest.approx(0.4854988026, abs=1e-7)
    assert result["is_significant"] is False


def test_log_rank_all_censored_returns_none() -> None:
    assert log_rank_test([1.0, 2.0], [False, False], [1.0, 2.0], [False, False]) is None


def test_log_rank_rejects_over_cap() -> None:
    big = [1.0] * (MAX_SURVIVAL_TOTAL + 1)
    with pytest.raises(ValueError):
        log_rank_test(big, [True] * len(big), [1.0, 2.0], [True, True])


# --- schema validation -------------------------------------------------------------------------


def test_survival_arm_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError):
        SurvivalArm(durations=[1.0, 2.0, 3.0], events_observed=[True, False])


def test_survival_arm_rejects_negative_duration() -> None:
    with pytest.raises(ValueError):
        SurvivalArm(durations=[-1.0], events_observed=[True])


# --- service layer -----------------------------------------------------------------------------


def _freireich_request(alpha: float = 0.05) -> SurvivalResultsRequest:
    return SurvivalResultsRequest(
        control_arm=SurvivalArm(durations=PLACEBO_DURATIONS, events_observed=PLACEBO_EVENTS),
        treatment_arm=SurvivalArm(durations=MP6_DURATIONS, events_observed=MP6_EVENTS),
        alpha=alpha,
    )


def test_service_rounds_and_builds_curves() -> None:
    response = analyze_survival_results(_freireich_request())
    assert response.chi_square == 16.7929  # rounded to 4 dp
    assert response.degrees_of_freedom == 1
    assert response.p_value == pytest.approx(0.000042, abs=1e-6)
    assert response.is_significant is True
    # Control here is placebo (all 21 relapse), treatment is 6-MP (9 relapse).
    assert response.observed_control == 21
    assert response.observed_treatment == 9
    assert response.n_control == 21
    assert response.n_treatment == 21
    # 6-MP treatment curve has one step per distinct event time.
    assert len(response.treatment_curve) == 7
    assert response.treatment_curve[0].survival == pytest.approx(0.857143, abs=1e-6)
    assert response.treatment_curve[0].at_risk == 21
    assert "χ²" in response.interpretation or "chi-square" in response.interpretation.lower()


def test_service_degenerate_all_censored_raises() -> None:
    request = SurvivalResultsRequest(
        control_arm=SurvivalArm(durations=[1.0, 2.0], events_observed=[False, False]),
        treatment_arm=SurvivalArm(durations=[1.0, 2.0], events_observed=[False, False]),
    )
    with pytest.raises(ValueError):
        analyze_survival_results(request)


# --- HTTP endpoint -----------------------------------------------------------------------------


def _freireich_payload() -> dict:
    return {
        "control_arm": {"durations": PLACEBO_DURATIONS, "events_observed": PLACEBO_EVENTS},
        "treatment_arm": {"durations": MP6_DURATIONS, "events_observed": MP6_EVENTS},
        "alpha": 0.05,
    }


def test_endpoint_survival_round_trip() -> None:
    client = TestClient(create_app())
    response = client.post("/api/v1/results/survival", json=_freireich_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["chi_square"] == 16.7929
    assert body["degrees_of_freedom"] == 1
    assert body["is_significant"] is True
    assert body["observed_treatment"] == 9
    assert len(body["treatment_curve"]) == 7
    assert body["treatment_curve"][0]["at_risk"] == 21
    assert body["treatment_curve"][0]["survival"] == pytest.approx(0.857143, abs=1e-6)
    assert body["control_curve"][0]["survival"] == pytest.approx(0.904762, abs=1e-6)


def test_endpoint_survival_all_censored_returns_400() -> None:
    client = TestClient(create_app())
    payload = {
        "control_arm": {"durations": [1, 2], "events_observed": [False, False]},
        "treatment_arm": {"durations": [1, 2], "events_observed": [False, False]},
    }
    response = client.post("/api/v1/results/survival", json=payload)
    assert response.status_code == 400


def test_endpoint_survival_mismatched_lengths_returns_422() -> None:
    client = TestClient(create_app())
    payload = {
        "control_arm": {"durations": [1, 2, 3], "events_observed": [True, False]},
        "treatment_arm": {"durations": [1, 2], "events_observed": [True, False]},
    }
    response = client.post("/api/v1/results/survival", json=payload)
    assert response.status_code == 422


def test_endpoint_localizes_via_accept_language() -> None:
    client = TestClient(create_app())
    payload = _freireich_payload()
    english = client.post("/api/v1/results/survival", json=payload)
    russian = client.post("/api/v1/results/survival", json=payload, headers={"Accept-Language": "ru"})
    assert english.status_code == 200 and russian.status_code == 200
    assert english.json()["verdict"] != russian.json()["verdict"]
    assert "alpha=0.050" in english.json()["verdict"]


# --- weighted k-sample log-rank (frozen against lifelines / statsmodels, see module docstring) ----

TWO_ARMS = [(MP6_DURATIONS, MP6_EVENTS), (PLACEBO_DURATIONS, PLACEBO_EVENTS)]
THREE_ARMS = [*TWO_ARMS, (THIRD_DURATIONS, THIRD_EVENTS)]


def test_k_sample_two_arm_unweighted_reduces_to_legacy_log_rank() -> None:
    generalized = weighted_k_sample_log_rank_test(TWO_ARMS)
    legacy = log_rank_test(MP6_DURATIONS, MP6_EVENTS, PLACEBO_DURATIONS, PLACEBO_EVENTS)
    assert generalized is not None and legacy is not None
    assert generalized["chi_square"] == pytest.approx(legacy["chi_square"], abs=1e-12)
    assert generalized["df"] == 1
    assert generalized["observed_by_arm"] == [legacy["observed1"], legacy["observed2"]]
    assert generalized["expected_by_arm"][0] == pytest.approx(legacy["expected1"], abs=1e-12)


def test_k_sample_three_arm_matches_lifelines_reference() -> None:
    result = weighted_k_sample_log_rank_test(THREE_ARMS)
    assert result is not None
    assert result["chi_square"] == pytest.approx(19.389263, abs=1e-5)
    assert result["df"] == 2
    assert result["p_value"] == pytest.approx(0.00006161, abs=1e-7)
    assert result["n_by_arm"] == [21, 21, 15]


def test_k_sample_is_invariant_to_arm_order() -> None:
    forward = weighted_k_sample_log_rank_test(THREE_ARMS)
    shuffled = weighted_k_sample_log_rank_test([THREE_ARMS[2], THREE_ARMS[0], THREE_ARMS[1]])
    assert forward is not None and shuffled is not None
    assert forward["chi_square"] == pytest.approx(shuffled["chi_square"], abs=1e-9)


def test_fleming_harrington_early_weights_match_reference() -> None:
    # FH(1, 0) = the classic G^rho early-difference test; frozen against lifelines AND statsmodels.
    result = weighted_k_sample_log_rank_test(TWO_ARMS, rho=1.0, gamma=0.0)
    assert result is not None
    assert result["chi_square"] == pytest.approx(14.457151, abs=1e-5)
    assert result["df"] == 1
    assert result["rho"] == 1.0 and result["gamma"] == 0.0


def test_fleming_harrington_late_weights_match_reference() -> None:
    result = weighted_k_sample_log_rank_test(TWO_ARMS, rho=0.0, gamma=1.0)
    assert result is not None
    assert result["chi_square"] == pytest.approx(13.048449, abs=1e-5)


def test_fleming_harrington_three_arm_matches_reference() -> None:
    result = weighted_k_sample_log_rank_test(THREE_ARMS, rho=1.0, gamma=0.0)
    assert result is not None
    assert result["chi_square"] == pytest.approx(16.701169, abs=1e-5)
    assert result["df"] == 2


def test_fleming_harrington_zero_exponents_equal_unweighted() -> None:
    weighted = weighted_k_sample_log_rank_test(THREE_ARMS, rho=0.0, gamma=0.0)
    unweighted = weighted_k_sample_log_rank_test(THREE_ARMS)
    assert weighted is not None and unweighted is not None
    assert weighted["chi_square"] == pytest.approx(unweighted["chi_square"], abs=1e-12)


def test_k_sample_all_censored_returns_none() -> None:
    arms = [([1.0, 2.0], [False, False]), ([1.5, 2.5], [False, False])]
    assert weighted_k_sample_log_rank_test(arms) is None


def test_k_sample_rejects_fewer_than_two_arms() -> None:
    with pytest.raises(ValueError, match="at least two arms"):
        weighted_k_sample_log_rank_test([(MP6_DURATIONS, MP6_EVENTS)])


def test_k_sample_rejects_negative_exponents() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        weighted_k_sample_log_rank_test(TWO_ARMS, rho=-1.0)


def test_k_sample_rejects_over_cap() -> None:
    half = MAX_SURVIVAL_TOTAL // 2 + 1
    arms = [([1.0] * half, [True] * half), ([1.0] * half, [True] * half)]
    with pytest.raises(ValueError, match="cap"):
        weighted_k_sample_log_rank_test(arms)


# --- k-sample / weighted service + endpoint ------------------------------------------------------


def _three_arm_payload() -> dict:
    return {
        "control_arm": {"durations": MP6_DURATIONS, "events_observed": MP6_EVENTS},
        "treatment_arm": {"durations": PLACEBO_DURATIONS, "events_observed": PLACEBO_EVENTS},
        "additional_arms": [
            {"durations": THIRD_DURATIONS, "events_observed": THIRD_EVENTS},
        ],
        "alpha": 0.05,
    }


def test_service_legacy_two_arm_payload_unchanged() -> None:
    """A pre-T3 request (no new fields) keeps its exact response: same χ², same detailed
    interpretation, log_rank echoed as the default test_type, no FH exponents."""
    response = analyze_survival_results(_freireich_request())
    assert response.chi_square == 16.7929
    assert response.test_type == "log_rank"
    assert response.fh_rho is None and response.fh_gamma is None
    assert len(response.arm_summaries) == 2
    assert response.arm_summaries[0].observed == response.observed_control
    assert response.additional_arm_curves == []


def test_endpoint_three_arm_round_trip() -> None:
    client = TestClient(create_app())
    response = client.post("/api/v1/results/survival", json=_three_arm_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["chi_square"] == pytest.approx(19.3893, abs=1e-4)
    assert body["degrees_of_freedom"] == 2
    assert body["p_value"] == pytest.approx(0.000062, abs=1e-6)
    assert body["is_significant"] is True
    assert body["test_type"] == "log_rank"
    assert [summary["n"] for summary in body["arm_summaries"]] == [21, 21, 15]
    assert len(body["additional_arm_curves"]) == 1
    assert len(body["additional_arm_curves"][0]) > 0
    # The k-sample interpretation names the test and the number of arms.
    assert "3" in body["interpretation"]


def test_endpoint_fleming_harrington_round_trip() -> None:
    client = TestClient(create_app())
    payload = {
        "control_arm": {"durations": MP6_DURATIONS, "events_observed": MP6_EVENTS},
        "treatment_arm": {"durations": PLACEBO_DURATIONS, "events_observed": PLACEBO_EVENTS},
        "test_type": "fleming_harrington",
        "fh_rho": 1.0,
        "fh_gamma": 0.0,
    }
    response = client.post("/api/v1/results/survival", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["chi_square"] == pytest.approx(14.4572, abs=1e-4)
    assert body["degrees_of_freedom"] == 1
    assert body["test_type"] == "fleming_harrington"
    assert body["fh_rho"] == 1.0 and body["fh_gamma"] == 0.0
    assert "Fleming" in body["interpretation"]


def test_endpoint_fleming_harrington_localizes_via_accept_language() -> None:
    client = TestClient(create_app())
    payload = {
        "control_arm": {"durations": MP6_DURATIONS, "events_observed": MP6_EVENTS},
        "treatment_arm": {"durations": PLACEBO_DURATIONS, "events_observed": PLACEBO_EVENTS},
        "test_type": "fleming_harrington",
    }
    response = client.post(
        "/api/v1/results/survival", json=payload, headers={"Accept-Language": "ru"}
    )
    assert response.status_code == 200
    assert "Флеминга" in response.json()["interpretation"]


def test_endpoint_rejects_too_many_additional_arms() -> None:
    client = TestClient(create_app())
    payload = _three_arm_payload()
    payload["additional_arms"] = [
        {"durations": [1.0, 2.0], "events_observed": [True, True]} for _ in range(9)
    ]
    response = client.post("/api/v1/results/survival", json=payload)
    assert response.status_code == 422
