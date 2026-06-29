"""Tests for the Yuen–Welch trimmed-means t-test (``stats/trimmed_t.py``): a robust two-sample
location test on γ-trimmed means with a Winsorized-variance standard error and Welch degrees of
freedom.

The expected statistic / df / p-value / CI constants below were cross-checked against
``scipy.stats.ttest_ind(treatment, control, trim=γ, equal_var=False)`` and its
``confidence_interval`` at authoring time and frozen, so the test stays stdlib-only and CI-safe (the
runtime tree carries no scipy). The agreement was exact on the statistic and df and within ~1e-8 on
the p-value / interval (the project's continued-fraction Student-t is accurate to ~1e-9). Covers: the
canonical robust case where shared outliers are trimmed away, the γ = 0 reduction to Welch's t, the
motivating case where one outlier masks a real shift from the ordinary t-test but not the trimmed one,
arm-swap antisymmetry, the effect of α on the interval width, the effective-size bookkeeping under
trimming, the degenerate guards, reproducibility, input validation, and Monte-Carlo proofs of type-I
control under H0 (including a heavy-tailed null) and power under a real shift.
"""

import math
import random
from statistics import fmean

import pytest

from app.backend.app.stats.trimmed_t import DEFAULT_TRIM, trimmed_means_t_test

# --- canonical cases vs scipy (frozen) --------------------------------------------------------

_CONTROL_OUTLIER = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 200.0]
_TREATMENT_OUTLIER = [12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0, 250.0]

_CONTROL_MILD = [5.2, 6.1, 7.3, 8.0, 9.5, 10.1, 11.2, 12.8, 13.0, 14.4, 15.9, 16.2]
_TREATMENT_MILD = [5.5, 6.0, 7.0, 8.4, 9.9, 10.6, 11.0, 12.2, 13.7, 14.0, 15.1, 17.8]


def test_canonical_matches_scipy() -> None:
    # Both arms carry one large outlier (200 / 250) that 20% trimming removes, leaving a clean +2
    # shift of two 9-point ramps. scipy.stats.ttest_ind(treatment, control, trim=0.2,
    # equal_var=False) -> statistic=1.1881770515720091, df=10.0, pvalue=0.2622164980237103,
    # CI(0.95)=(-1.7505165404781318, 5.750516540478132).
    result = trimmed_means_t_test(_CONTROL_OUTLIER, _TREATMENT_OUTLIER, trim=0.2, alpha=0.05)
    assert result is not None
    assert result["control_trimmed_mean"] == pytest.approx(14.5)
    assert result["treatment_trimmed_mean"] == pytest.approx(16.5)
    assert result["observed_diff"] == pytest.approx(2.0, abs=1e-9)
    assert result["test_statistic"] == pytest.approx(1.1881770515720091, abs=1e-9)
    assert result["degrees_of_freedom"] == pytest.approx(10.0, abs=1e-9)
    assert result["p_value"] == pytest.approx(0.2622164980237103, abs=1e-7)
    assert result["ci_lower"] == pytest.approx(-1.7505165404781318, abs=1e-6)
    assert result["ci_upper"] == pytest.approx(5.750516540478132, abs=1e-6)
    assert result["control_effective_n"] == 6
    assert result["treatment_effective_n"] == 6
    assert result["ci_level"] == pytest.approx(0.95)
    assert result["is_significant"] is False


def test_mild_case_matches_scipy() -> None:
    # No outliers, near-identical arms. scipy(trim=0.2, equal_var=False) -> statistic=
    # 0.034325725975409574, df=13.994613051583126, pvalue=0.9731022011121535,
    # CI(0.95)=(-3.8428510106171565, 3.9678510106171565).
    result = trimmed_means_t_test(_CONTROL_MILD, _TREATMENT_MILD, trim=0.2, alpha=0.05)
    assert result is not None
    assert result["observed_diff"] == pytest.approx(0.0625, abs=1e-9)
    assert result["test_statistic"] == pytest.approx(0.034325725975409574, abs=1e-9)
    assert result["degrees_of_freedom"] == pytest.approx(13.994613051583126, abs=1e-9)
    assert result["p_value"] == pytest.approx(0.9731022011121535, abs=1e-7)
    assert result["ci_lower"] == pytest.approx(-3.8428510106171565, abs=1e-6)
    assert result["ci_upper"] == pytest.approx(3.9678510106171565, abs=1e-6)
    assert result["control_effective_n"] == 8
    assert result["treatment_effective_n"] == 8


def test_trim_zero_reduces_to_welch() -> None:
    # γ = 0 must reproduce Welch's unequal-variance t-test exactly. scipy.stats.ttest_ind(treatment,
    # control, equal_var=False) -> statistic=0.7223151185146153, df=8.672131147540984,
    # pvalue=0.4891192243243059.
    control = [3.0, 5.0, 7.0, 9.0, 11.0, 13.0]
    treatment = [4.0, 6.0, 8.0, 10.0, 12.0, 20.0]
    result = trimmed_means_t_test(control, treatment, trim=0.0, alpha=0.05)
    assert result is not None
    # No trimming: trimmed means are the arithmetic means, effective N is the full N.
    assert result["control_trimmed_mean"] == pytest.approx(fmean(control))
    assert result["treatment_trimmed_mean"] == pytest.approx(fmean(treatment))
    assert result["control_effective_n"] == len(control)
    assert result["treatment_effective_n"] == len(treatment)
    assert result["test_statistic"] == pytest.approx(0.7223151185146153, abs=1e-9)
    assert result["degrees_of_freedom"] == pytest.approx(8.672131147540984, abs=1e-9)
    assert result["p_value"] == pytest.approx(0.4891192243243059, abs=1e-7)


def test_outlier_masks_real_shift_only_for_untrimmed() -> None:
    """The motivating case: a clean +3 location shift with one extreme negative outlier in the
    treatment arm. The ordinary (γ = 0) t-test is dragged to a negative effect and misses it; the
    20%-trimmed test removes the outlier and recovers a sharply significant +3. scipy agrees on both
    p-values (welch pvalue=0.4177334104019781, trimmed pvalue≈9.18e-12)."""
    control = [round(10 + i * 0.1, 4) for i in range(30)]
    treatment = [round(value + 3.0, 4) for value in control]
    treatment[0] = -500.0

    welch = trimmed_means_t_test(control, treatment, trim=0.0, alpha=0.05)
    trimmed = trimmed_means_t_test(control, treatment, trim=0.2, alpha=0.05)
    assert welch is not None and trimmed is not None

    # Untrimmed: the −500 outlier flips the effect negative and the test is not significant.
    assert welch["observed_diff"] < 0
    assert welch["p_value"] == pytest.approx(0.4177334104019781, abs=1e-7)
    assert welch["is_significant"] is False

    # Trimmed: the outlier is gone, the true +3 shift is recovered and is significant.
    assert trimmed["observed_diff"] == pytest.approx(3.0, abs=1e-9)
    assert trimmed["p_value"] < 1e-9
    assert trimmed["is_significant"] is True
    assert trimmed["ci_lower"] > 0  # CI excludes zero


def test_arm_swap_antisymmetry() -> None:
    forward = trimmed_means_t_test(_CONTROL_MILD, _TREATMENT_MILD, trim=0.2, alpha=0.05)
    swapped = trimmed_means_t_test(_TREATMENT_MILD, _CONTROL_MILD, trim=0.2, alpha=0.05)
    assert forward is not None and swapped is not None
    # Effect and statistic flip sign; the two-sided p-value, df and CI width are unchanged.
    assert forward["observed_diff"] == pytest.approx(-swapped["observed_diff"], abs=1e-9)
    assert forward["test_statistic"] == pytest.approx(-swapped["test_statistic"], abs=1e-9)
    assert forward["p_value"] == pytest.approx(swapped["p_value"], abs=1e-12)
    assert forward["degrees_of_freedom"] == pytest.approx(swapped["degrees_of_freedom"], abs=1e-9)
    forward_width = forward["ci_upper"] - forward["ci_lower"]
    swapped_width = swapped["ci_upper"] - swapped["ci_lower"]
    assert forward_width == pytest.approx(swapped_width, abs=1e-9)


def test_smaller_alpha_widens_interval_without_changing_p() -> None:
    wide = trimmed_means_t_test(_CONTROL_MILD, _TREATMENT_MILD, trim=0.2, alpha=0.01)
    narrow = trimmed_means_t_test(_CONTROL_MILD, _TREATMENT_MILD, trim=0.2, alpha=0.05)
    assert wide is not None and narrow is not None
    # α only sets the interval width and the verdict threshold, not the p-value or statistic.
    assert wide["p_value"] == pytest.approx(narrow["p_value"], abs=1e-12)
    assert wide["test_statistic"] == pytest.approx(narrow["test_statistic"], abs=1e-12)
    assert (wide["ci_upper"] - wide["ci_lower"]) > (narrow["ci_upper"] - narrow["ci_lower"])
    assert wide["ci_level"] == pytest.approx(0.99)


def test_trim_fraction_sets_effective_size() -> None:
    # n = 10 per arm: γ=0.1 -> g=1, h=8; γ=0.2 -> g=2, h=6; γ=0.3 -> g=3, h=4.
    for trim, expected_h in [(0.1, 8), (0.2, 6), (0.3, 4)]:
        result = trimmed_means_t_test(_CONTROL_OUTLIER, _TREATMENT_OUTLIER, trim=trim, alpha=0.05)
        assert result is not None
        assert result["control_effective_n"] == expected_h
        assert result["treatment_effective_n"] == expected_h
        assert result["trim"] == trim


def test_default_trim_is_twenty_percent() -> None:
    assert DEFAULT_TRIM == 0.2
    explicit = trimmed_means_t_test(_CONTROL_MILD, _TREATMENT_MILD, trim=0.2, alpha=0.05)
    defaulted = trimmed_means_t_test(_CONTROL_MILD, _TREATMENT_MILD, alpha=0.05)
    assert explicit is not None and defaulted is not None
    assert defaulted["test_statistic"] == pytest.approx(explicit["test_statistic"], abs=1e-12)


def test_reproducible() -> None:
    first = trimmed_means_t_test(_CONTROL_MILD, _TREATMENT_MILD, trim=0.2, alpha=0.05)
    second = trimmed_means_t_test(_CONTROL_MILD, _TREATMENT_MILD, trim=0.2, alpha=0.05)
    assert first == second


# --- degenerate guards ------------------------------------------------------------------------


def test_effective_size_below_two_returns_none() -> None:
    # n=3, γ=0.4 -> g=1, h=1: too few untrimmed observations to estimate a trimmed-mean variance.
    assert trimmed_means_t_test([1.0, 2.0, 3.0], [4.0, 5.0, 6.0], trim=0.4, alpha=0.05) is None


def test_zero_winsorized_variance_returns_none() -> None:
    # Constant arms (even if their levels differ) have zero Winsorized variance — a parametric
    # location test has no standard error, so the test is not evaluable.
    assert trimmed_means_t_test([5.0, 5.0, 5.0, 5.0], [7.0, 7.0, 7.0, 7.0], trim=0.0) is None


def test_empty_or_singleton_arm_returns_none() -> None:
    assert trimmed_means_t_test([1.0], [1.0, 2.0, 3.0], trim=0.2) is None
    assert trimmed_means_t_test([1.0, 2.0, 3.0], [5.0], trim=0.2) is None


# --- input validation -------------------------------------------------------------------------


@pytest.mark.parametrize("alpha", [0.0, 1.0, -0.1, 1.5])
def test_invalid_alpha_raises(alpha: float) -> None:
    with pytest.raises(ValueError):
        trimmed_means_t_test(_CONTROL_MILD, _TREATMENT_MILD, trim=0.2, alpha=alpha)


@pytest.mark.parametrize("trim", [-0.1, 0.5, 0.6, 1.0])
def test_invalid_trim_raises(trim: float) -> None:
    with pytest.raises(ValueError):
        trimmed_means_t_test(_CONTROL_MILD, _TREATMENT_MILD, trim=trim, alpha=0.05)


def test_non_finite_values_raise() -> None:
    with pytest.raises(ValueError):
        trimmed_means_t_test([1.0, 2.0, math.inf], [1.0, 2.0, 3.0], trim=0.0)
    with pytest.raises(ValueError):
        trimmed_means_t_test([1.0, 2.0, 3.0], [1.0, math.nan, 3.0], trim=0.0)


# --- Monte-Carlo properties -------------------------------------------------------------------


def test_type_one_error_controlled_under_null_normal() -> None:
    """Under H0 (both arms drawn from one normal) the rejection rate must sit near α."""
    rng = random.Random(20240630)
    alpha = 0.05
    trials = 2000
    rejections = 0
    for _ in range(trials):
        control = [rng.gauss(50.0, 8.0) for _ in range(40)]
        treatment = [rng.gauss(50.0, 8.0) for _ in range(40)]
        result = trimmed_means_t_test(control, treatment, trim=0.2, alpha=alpha)
        if result is not None and result["is_significant"]:
            rejections += 1
    rate = rejections / trials
    assert abs(rate - alpha) < 0.02


def test_type_one_error_controlled_under_heavy_tailed_null() -> None:
    """The selling point: even with a heavy-tailed (lognormal) null where the ordinary t-test's
    nominal α is unreliable, the trimmed test keeps the rejection rate near α."""
    rng = random.Random(99991)
    alpha = 0.05
    trials = 2000
    rejections = 0
    for _ in range(trials):
        control = [rng.lognormvariate(0.0, 1.0) for _ in range(50)]
        treatment = [rng.lognormvariate(0.0, 1.0) for _ in range(50)]
        result = trimmed_means_t_test(control, treatment, trim=0.2, alpha=alpha)
        if result is not None and result["is_significant"]:
            rejections += 1
    rate = rejections / trials
    assert abs(rate - alpha) < 0.02


def test_power_under_real_shift() -> None:
    """Under a genuine location shift the test rejects the great majority of the time."""
    rng = random.Random(424242)
    alpha = 0.05
    trials = 500
    rejections = 0
    for _ in range(trials):
        control = [rng.gauss(20.0, 5.0) for _ in range(60)]
        treatment = [rng.gauss(24.0, 5.0) for _ in range(60)]
        result = trimmed_means_t_test(control, treatment, trim=0.2, alpha=alpha)
        if result is not None and result["is_significant"]:
            rejections += 1
    assert rejections / trials > 0.9
