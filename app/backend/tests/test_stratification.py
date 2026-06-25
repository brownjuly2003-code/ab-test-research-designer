"""Post-stratification math (F3b): per-arm estimate variances, the size-weighted combine
(Δ = Σ (n_s/N)·Δ_s, Var = Σ (n_s/N)²·Var(Δ_s)), and the variance-reduction reporting.

Verified against the post-stratification estimator (Miratrix, Sekhon & Yu 2013): a single
stratum reduces to the unadjusted difference, the combine matches a hand calculation, and the
reduction may be negative when strata are unhelpful.
"""

from math import sqrt
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.stats import stratification


# --- per-arm point + variance helpers -------------------------------------------------


def test_binary_point_variance_is_rate_and_wald_variance() -> None:
    point, variance = stratification.binary_point_variance(3, 10)
    assert point == pytest.approx(0.3)
    assert variance == pytest.approx(0.3 * 0.7 / 10)


def test_binary_point_variance_zero_variance_arm_allowed() -> None:
    # p = 1 (or 0) is a valid arm; it contributes 0 variance, like the unpooled binary comparison.
    point, variance = stratification.binary_point_variance(5, 5)
    assert point == 1.0
    assert variance == 0.0


def test_binary_point_variance_none_for_empty_arm() -> None:
    assert stratification.binary_point_variance(0, 0) is None


def test_continuous_point_variance_matches_sample_variance_over_n() -> None:
    values = [10.0, 20.0, 30.0, 40.0]
    n = len(values)
    point, variance = stratification.continuous_point_variance(
        sum(values), sum(v * v for v in values), n
    )
    assert point == pytest.approx(25.0)
    sample_variance = sum((v - 25.0) ** 2 for v in values) / (n - 1)
    assert variance == pytest.approx(sample_variance / n)


def test_continuous_point_variance_none_under_two_users() -> None:
    assert stratification.continuous_point_variance(10.0, 100.0, 1) is None


def test_continuous_point_variance_clamps_negative_roundoff() -> None:
    # Identical values -> exact sample variance 0; tiny float round-off must not go negative.
    point, variance = stratification.continuous_point_variance(30.0, 300.0, 3)
    assert point == pytest.approx(10.0)
    assert variance == 0.0


def test_stratum_difference_is_treatment_minus_control_unpooled() -> None:
    difference = stratification.stratum_difference((0.20, 0.0016), (0.30, 0.0021))
    assert difference["delta"] == pytest.approx(0.10)
    assert difference["variance"] == pytest.approx(0.0016 + 0.0021)


# --- the size-weighted combine --------------------------------------------------------


def test_single_stratum_equals_the_unadjusted_difference() -> None:
    # One stratum carries weight 1, so the combined effect/variance are exactly that stratum's
    # (the naive unstratified difference), and the reduction against the same variance is 0.
    difference = stratification.stratum_difference((0.20, 0.0016), (0.30, 0.0021))
    combined = stratification.combine_strata(
        [{"n": 200, "delta": difference["delta"], "variance": difference["variance"]}]
    )
    assert combined is not None
    assert combined["effect"] == pytest.approx(0.10)
    assert combined["variance"] == pytest.approx(0.0037)
    assert combined["num_strata"] == 1
    assert combined["total_users"] == 200
    assert stratification.variance_reduction_pct(
        difference["variance"], combined["variance"]
    ) == pytest.approx(0.0)


def test_weighted_combine_matches_hand_calculation() -> None:
    strata = [
        {"n": 100, "delta": 0.10, "variance": 0.004},
        {"n": 300, "delta": 0.02, "variance": 0.001},
    ]
    combined = stratification.combine_strata(strata, alpha=0.05)
    assert combined is not None
    total = 400
    w1, w2 = 100 / total, 300 / total
    expected_effect = w1 * 0.10 + w2 * 0.02
    expected_variance = w1 * w1 * 0.004 + w2 * w2 * 0.001
    assert combined["effect"] == pytest.approx(expected_effect)
    assert combined["variance"] == pytest.approx(expected_variance)
    assert combined["standard_error"] == pytest.approx(sqrt(expected_variance))
    assert combined["test_statistic"] == pytest.approx(expected_effect / sqrt(expected_variance))
    # Symmetric two-sided 95% CI around the effect.
    half_width = combined["ci_upper"] - combined["effect"]
    assert combined["effect"] - combined["ci_lower"] == pytest.approx(half_width)
    assert combined["ci_level"] == pytest.approx(0.95)
    assert combined["num_strata"] == 2


def test_combine_drops_unusable_strata() -> None:
    # n <= 0 and non-finite entries are dropped; only the valid stratum drives the combine.
    strata = [
        {"n": 0, "delta": 5.0, "variance": 1.0},
        {"n": 50, "delta": 0.20, "variance": 0.01},
    ]
    combined = stratification.combine_strata(strata)
    assert combined is not None
    assert combined["num_strata"] == 1
    assert combined["effect"] == pytest.approx(0.20)
    assert combined["variance"] == pytest.approx(0.01)


def test_combine_none_when_no_stratum_usable() -> None:
    assert stratification.combine_strata([]) is None
    assert stratification.combine_strata([{"n": 0, "delta": 1.0, "variance": 1.0}]) is None


def test_combine_none_when_combined_variance_zero() -> None:
    # Every stratum has zero variance (e.g. degenerate arms) -> no usable signal.
    assert stratification.combine_strata([{"n": 10, "delta": 0.0, "variance": 0.0}]) is None


def test_combine_rejects_out_of_range_alpha() -> None:
    with pytest.raises(ValueError):
        stratification.combine_strata([{"n": 10, "delta": 1.0, "variance": 1.0}], alpha=0)
    with pytest.raises(ValueError):
        stratification.combine_strata([{"n": 10, "delta": 1.0, "variance": 1.0}], alpha=1)


def test_significant_effect_is_flagged() -> None:
    # A large effect relative to a small variance crosses the 95% threshold.
    combined = stratification.combine_strata([{"n": 400, "delta": 1.0, "variance": 0.01}])
    assert combined is not None
    assert combined["is_significant"] is True
    assert combined["p_value"] < 0.05


# --- variance reduction reporting -----------------------------------------------------


def test_variance_reduction_positive_when_stratified_variance_is_smaller() -> None:
    assert stratification.variance_reduction_pct(1.0, 0.25) == pytest.approx(75.0)


def test_variance_reduction_can_be_negative_when_stratification_hurts() -> None:
    # Miratrix et al.: many sparse, poorly-chosen strata can *increase* variance — reported
    # honestly rather than clamped to zero.
    assert stratification.variance_reduction_pct(1.0, 1.5) == pytest.approx(-50.0)


def test_variance_reduction_none_for_nonpositive_pooled_variance() -> None:
    assert stratification.variance_reduction_pct(0.0, 0.0) is None
    assert stratification.variance_reduction_pct(-1.0, 0.5) is None
