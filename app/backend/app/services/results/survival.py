"""Time-to-event analyzers (log-rank / Fleming–Harrington / Cox PH)."""
from __future__ import annotations

from typing import Any

from app.backend.app.i18n import translate
from app.backend.app.schemas.api import (
    SurvivalArmSummary,
    SurvivalCurvePoint,
    SurvivalResultsRequest,
    SurvivalResultsResponse,
)
from app.backend.app.stats.cox_ph import cox_ph_treatment_effect
from app.backend.app.stats.survival import (
    kaplan_meier_estimate,
    weighted_k_sample_log_rank_test,
)

from .common import _significance_text


def analyze_survival_results(request: SurvivalResultsRequest) -> SurvivalResultsResponse:
    """Kaplan–Meier survival curves + a log-rank-family test over ``k >= 2`` arms.

    Separate from ``analyze_results`` because the input is time-to-event (a duration plus a censoring
    flag per subject) and the outcome is per-arm survival curves plus an omnibus statistic, not the
    scalar effect + confidence interval ``ResultsResponse`` carries. All requests run through the one
    weighted k-sample statistic (``ρ = γ = 0`` for the plain log-rank branch — for two arms that is
    numerically identical to the classic Mantel–Cox formula, pinned by a test). A fully censored
    comparison (or an arm contributing no information, making the covariance singular) leaves the
    statistic undefined; the stats layer returns ``None`` and this raises ``ValueError``, which the
    global handler maps to HTTP 400 rather than inventing a chi-square.
    """
    if request.test_type == "cox":
        return _analyze_cox_survival(request)

    arms = [request.control_arm, request.treatment_arm, *request.additional_arms]
    is_weighted = request.test_type == "fleming_harrington"
    rho = request.fh_rho if is_weighted else 0.0
    gamma = request.fh_gamma if is_weighted else 0.0
    result = weighted_k_sample_log_rank_test(
        [(arm.durations, arm.events_observed) for arm in arms],
        request.alpha,
        rho=rho,
        gamma=gamma,
    )
    if result is None:
        raise ValueError(translate("errors.schemas.survival_no_events"))

    curves = [
        [
            _survival_curve_point(point)
            for point in kaplan_meier_estimate(arm.durations, arm.events_observed, request.alpha)
        ]
        for arm in arms
    ]
    arm_summaries = [
        SurvivalArmSummary(
            n=result["n_by_arm"][index],
            observed=result["observed_by_arm"][index],
            expected=round(result["expected_by_arm"][index], 4),
        )
        for index in range(len(arms))
    ]

    is_significant = result["is_significant"]
    if len(arms) == 2 and not is_weighted:
        # The classic two-arm log-rank keeps its established, more detailed interpretation.
        interpretation = translate(
            "results.interpretation.log_rank",
            {
                "chiSquare": f"{result['chi_square']:.4f}",
                "pValue": f"{result['p_value']:.6f}",
                "observedControl": str(result["observed_by_arm"][0]),
                "expectedControl": f"{result['expected_by_arm'][0]:.4f}",
                "observedTreatment": str(result["observed_by_arm"][1]),
                "expectedTreatment": f"{result['expected_by_arm'][1]:.4f}",
                "nControl": str(result["n_by_arm"][0]),
                "nTreatment": str(result["n_by_arm"][1]),
                "significance": _significance_text(is_significant),
            },
        )
    else:
        test_name = (
            translate(
                "results.survival.test_name.fleming_harrington",
                {"rho": f"{rho:g}", "gamma": f"{gamma:g}"},
            )
            if is_weighted
            else translate("results.survival.test_name.log_rank")
        )
        interpretation = translate(
            "results.interpretation.log_rank_family",
            {
                "testName": test_name,
                "numArms": str(len(arms)),
                "chiSquare": f"{result['chi_square']:.4f}",
                "df": str(result["df"]),
                "pValue": f"{result['p_value']:.6f}",
                "significance": _significance_text(is_significant),
            },
        )

    return SurvivalResultsResponse(
        chi_square=round(result["chi_square"], 4),
        degrees_of_freedom=result["df"],
        p_value=round(result["p_value"], 6),
        is_significant=is_significant,
        test_type=request.test_type,
        fh_rho=rho if is_weighted else None,
        fh_gamma=gamma if is_weighted else None,
        observed_control=arm_summaries[0].observed,
        expected_control=arm_summaries[0].expected,
        observed_treatment=arm_summaries[1].observed,
        expected_treatment=arm_summaries[1].expected,
        n_control=arm_summaries[0].n,
        n_treatment=arm_summaries[1].n,
        arm_summaries=arm_summaries,
        control_curve=curves[0],
        treatment_curve=curves[1],
        additional_arm_curves=curves[2:],
        verdict=_survival_verdict(is_significant, request.alpha),
        interpretation=interpretation,
    )


def _analyze_cox_survival(request: SurvivalResultsRequest) -> SurvivalResultsResponse:
    """Cox proportional-hazards branch: the treatment-effect hazard ratio with Wald inference.

    Reuses the survival response shape — ``chi_square`` carries the Wald ``z²`` (1 df) and the
    ``hazard_ratio*`` effect-size fields are populated. The descriptive per-arm ``expected`` counts
    come from an unweighted log-rank pass over the same data (risk-set expectations are
    test-agnostic); when even that is undefined the observed counts stand in, which cannot happen
    for a fit that converged (a converged Cox fit needs events in both arms' risk experience).
    """
    control = request.control_arm
    treatment = request.treatment_arm
    result = cox_ph_treatment_effect(
        control.durations,
        control.events_observed,
        treatment.durations,
        treatment.events_observed,
        request.alpha,
    )
    if result is None:
        raise ValueError(translate("errors.schemas.survival_cox_undefined"))

    log_rank = weighted_k_sample_log_rank_test(
        [
            (control.durations, control.events_observed),
            (treatment.durations, treatment.events_observed),
        ],
        request.alpha,
    )
    expected = (
        log_rank["expected_by_arm"]
        if log_rank is not None
        else [float(result["events_control"]), float(result["events_treatment"])]
    )
    arm_summaries = [
        SurvivalArmSummary(
            n=int(result["n_control"]),
            observed=int(result["events_control"]),
            expected=round(expected[0], 4),
        ),
        SurvivalArmSummary(
            n=int(result["n_treatment"]),
            observed=int(result["events_treatment"]),
            expected=round(expected[1], 4),
        ),
    ]
    curves = [
        [
            _survival_curve_point(point)
            for point in kaplan_meier_estimate(arm.durations, arm.events_observed, request.alpha)
        ]
        for arm in (control, treatment)
    ]

    is_significant = bool(result["is_significant"])
    interpretation = translate(
        "results.interpretation.cox_ph",
        {
            "hazardRatio": f"{result['hazard_ratio']:.4f}",
            "ciLevel": f"{(1 - request.alpha) * 100:.1f}",
            "ciLower": f"{result['hr_ci_lower']:.4f}",
            "ciUpper": f"{result['hr_ci_upper']:.4f}",
            "z": f"{result['z_statistic']:.4f}",
            "pValue": f"{result['p_value']:.6f}",
            "significance": _significance_text(is_significant),
        },
    )
    return SurvivalResultsResponse(
        chi_square=round(float(result["wald_chi_square"]), 4),
        degrees_of_freedom=1,
        p_value=round(float(result["p_value"]), 6),
        is_significant=is_significant,
        test_type="cox",
        hazard_ratio=round(float(result["hazard_ratio"]), 4),
        hazard_ratio_ci_lower=round(float(result["hr_ci_lower"]), 4),
        hazard_ratio_ci_upper=round(float(result["hr_ci_upper"]), 4),
        log_hazard_ratio=round(float(result["log_hazard_ratio"]), 6),
        log_hazard_ratio_se=round(float(result["standard_error"]), 6),
        observed_control=arm_summaries[0].observed,
        expected_control=arm_summaries[0].expected,
        observed_treatment=arm_summaries[1].observed,
        expected_treatment=arm_summaries[1].expected,
        n_control=arm_summaries[0].n,
        n_treatment=arm_summaries[1].n,
        arm_summaries=arm_summaries,
        control_curve=curves[0],
        treatment_curve=curves[1],
        verdict=_survival_verdict(is_significant, request.alpha),
        interpretation=interpretation,
    )


def _survival_curve_point(point: dict[str, Any]) -> SurvivalCurvePoint:
    return SurvivalCurvePoint(
        time=point["time"],
        survival=round(point["survival"], 6),
        at_risk=point["at_risk"],
        n_events=point["n_events"],
        std_error=round(point["std_error"], 6),
        ci_lower=round(point["ci_lower"], 6),
        ci_upper=round(point["ci_upper"], 6),
    )


def _survival_verdict(is_significant: bool, alpha: float) -> str:
    # The log-rank test reports only whether the two survival curves differ (no signed direction), so
    # the verdict is a two-state call, mirroring the omnibus / categorical analyzers.
    return translate(
        "results.survival.verdict_difference"
        if is_significant
        else "results.survival.verdict_no_difference",
        {"alpha": f"{alpha:.3f}"},
    )

