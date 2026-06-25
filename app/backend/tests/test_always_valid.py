"""Tests for the always-valid (mSPRT) inference layer.

The centerpiece is an empirical Monte-Carlo demonstration that the always-valid p-value controls
type-I error under *continuous monitoring* (peek at every look, stop whenever), while a naive fixed
two-proportion z-test on the same peeked data inflates well past alpha. That contrast is the whole
reason the method exists, so it is verified directly rather than trusted from the closed form.
"""

import random
import sys
from math import exp, log, sqrt
from pathlib import Path
from statistics import NormalDist

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.stats.always_valid import (
    always_valid_p_value,
    confidence_sequence,
    default_mixture_variance,
    evaluate_always_valid,
    msprt_log_likelihood_ratio,
)


# --------------------------------------------------------------------------------------
# Closed-form reference values (hand-computed from the formulae in the module docstring).
# effect = 0.02, V = 1e-4 (SE = 0.01), tau^2 = 4e-4 (tau = 0.02), alpha = 0.05.
#   ln(Lambda) = -0.5*ln(5e-4/1e-4) + 4e-4*0.02^2 / (2*1e-4*5e-4)
#              = -0.5*ln(5) + 1.6   = -0.804719 + 1.6 = 0.795281
#   Lambda     = exp(0.795281)      = 2.215065
#   p          = 1/Lambda           = 0.4514543
#   radius     = sqrt( (2*1e-4*5e-4/4e-4) * (ln(20) + 0.5*ln(5)) )
#              = sqrt( 2.5e-4 * (2.995732 + 0.804719) ) = sqrt(9.50113e-4) = 0.0308239
# --------------------------------------------------------------------------------------
_REF_EFFECT = 0.02
_REF_VARIANCE = 1e-4
_REF_TAU_SQUARED = 4e-4


def test_log_likelihood_ratio_matches_closed_form() -> None:
    log_lr = msprt_log_likelihood_ratio(_REF_EFFECT, _REF_VARIANCE, _REF_TAU_SQUARED)
    assert log_lr == pytest.approx(0.795281, abs=1e-5)


def test_p_value_matches_closed_form() -> None:
    p_value = always_valid_p_value(_REF_EFFECT, _REF_VARIANCE, _REF_TAU_SQUARED)
    assert p_value == pytest.approx(0.4514543, abs=1e-5)


def test_confidence_sequence_matches_closed_form() -> None:
    lower, upper = confidence_sequence(_REF_EFFECT, _REF_VARIANCE, _REF_TAU_SQUARED, alpha=0.05)
    assert lower == pytest.approx(_REF_EFFECT - 0.0308239, abs=1e-6)
    assert upper == pytest.approx(_REF_EFFECT + 0.0308239, abs=1e-6)


def test_zero_effect_gives_p_value_one() -> None:
    # No observed difference -> Lambda_n < 1 -> p clamps to exactly 1.
    assert always_valid_p_value(0.0, _REF_VARIANCE, _REF_TAU_SQUARED) == 1.0


def test_p_value_decreases_as_effect_grows() -> None:
    effects = [0.0, 0.01, 0.02, 0.04, 0.08]
    p_values = [always_valid_p_value(e, _REF_VARIANCE, _REF_TAU_SQUARED) for e in effects]
    assert all(p_values[i] >= p_values[i + 1] for i in range(len(p_values) - 1))
    assert p_values[-1] < p_values[0]


def test_significance_is_dual_to_confidence_sequence_excluding_zero() -> None:
    # The test (p < alpha) and the confidence sequence (excludes 0) must agree at every point.
    for effect in [0.0, 0.01, 0.02, 0.03, 0.05, 0.08, -0.04]:
        for variance in [1e-5, 1e-4, 5e-4]:
            result = evaluate_always_valid(effect, variance, _REF_TAU_SQUARED, alpha=0.05)
            lower, upper = result["ci_sequence_lower"], result["ci_sequence_upper"]
            excludes_zero = lower > 0 or upper < 0
            assert result["is_significant"] == excludes_zero


def test_confidence_sequence_is_wider_than_fixed_horizon_ci() -> None:
    # Anytime-valid intervals pay for the right to peek, so they must be wider than the
    # fixed-horizon (1 - alpha) z-interval at the same variance.
    lower, upper = confidence_sequence(_REF_EFFECT, _REF_VARIANCE, _REF_TAU_SQUARED, alpha=0.05)
    anytime_half_width = (upper - lower) / 2
    fixed_half_width = NormalDist().inv_cdf(1 - 0.05 / 2) * sqrt(_REF_VARIANCE)
    assert anytime_half_width > fixed_half_width


def test_default_mixture_variance_is_squared_effect() -> None:
    assert default_mixture_variance(0.02) == pytest.approx(4e-4)
    assert default_mixture_variance(0.1) == pytest.approx(0.01)


@pytest.mark.parametrize(
    "bad_call",
    [
        lambda: always_valid_p_value(0.02, 0.0, 4e-4),  # variance must be > 0
        lambda: always_valid_p_value(0.02, -1e-4, 4e-4),
        lambda: always_valid_p_value(0.02, 1e-4, 0.0),  # tau^2 must be > 0
        lambda: confidence_sequence(0.02, 1e-4, 4e-4, alpha=0.0),  # alpha in (0,1)
        lambda: confidence_sequence(0.02, 1e-4, 4e-4, alpha=1.0),
        lambda: default_mixture_variance(0.0),  # expected_effect must be > 0
    ],
)
def test_invalid_inputs_raise(bad_call) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        bad_call()


# --------------------------------------------------------------------------------------
# Monte-Carlo: anytime type-I control under continuous monitoring.
# --------------------------------------------------------------------------------------
def _simulate_continuous_peeking(
    p_control: float,
    p_treatment: float,
    *,
    tau_squared: float,
    alpha: float,
    n_sim: int,
    max_n: int,
    step: int,
    seed: int,
) -> tuple[float, float]:
    """Run ``n_sim`` two-arm experiments, peeking every ``step`` users up to ``max_n`` per arm.

    Returns ``(msprt_fraction, naive_fraction)`` — the share of experiments where the always-valid
    p-value (resp. a naive fixed-horizon two-proportion z-test) ever dropped below ``alpha``.
    """
    rng = random.Random(seed)
    normal = NormalDist()
    msprt_rejections = 0
    naive_rejections = 0

    for _ in range(n_sim):
        c_conv = c_n = t_conv = t_n = 0
        msprt_hit = naive_hit = False
        for users in range(1, max_n + 1):
            c_n += 1
            if rng.random() < p_control:
                c_conv += 1
            t_n += 1
            if rng.random() < p_treatment:
                t_conv += 1
            if users < step or users % step != 0:
                continue
            rate_c = c_conv / c_n
            rate_t = t_conv / t_n
            variance = rate_c * (1 - rate_c) / c_n + rate_t * (1 - rate_t) / t_n
            if variance <= 0:
                continue
            effect = rate_t - rate_c
            if not msprt_hit and always_valid_p_value(effect, variance, tau_squared) < alpha:
                msprt_hit = True
            if not naive_hit:
                z = effect / sqrt(variance)
                naive_p = 2 * (1 - normal.cdf(abs(z)))
                if naive_p < alpha:
                    naive_hit = True
            if msprt_hit and naive_hit:
                break
        msprt_rejections += int(msprt_hit)
        naive_rejections += int(naive_hit)

    return msprt_rejections / n_sim, naive_rejections / n_sim


def test_anytime_type_one_error_is_controlled_while_naive_peeking_inflates() -> None:
    # Null: both arms share the same conversion rate, so any "win" is a false positive.
    msprt_fp, naive_fp = _simulate_continuous_peeking(
        p_control=0.20,
        p_treatment=0.20,
        tau_squared=default_mixture_variance(0.02),
        alpha=0.05,
        n_sim=500,
        max_n=1500,
        step=30,
        seed=20260625,
    )
    # The always-valid p-value keeps the false-positive rate at or below alpha despite peeking
    # at 50 looks; the small cushion absorbs Monte-Carlo noise.
    assert msprt_fp <= 0.07, f"always-valid anytime FPR too high: {msprt_fp}"
    # The naive fixed-horizon test applied at every look inflates clearly past alpha — this is the
    # "peeking problem" the method solves. It must be visibly worse than the always-valid rate.
    assert naive_fp > 0.10, f"expected naive peeking to inflate, got {naive_fp}"
    assert naive_fp > msprt_fp


def _simulate_coverage(
    p_control: float,
    p_treatment: float,
    *,
    tau_squared: float,
    alpha: float,
    n_sim: int,
    max_n: int,
    step: int,
    seed: int,
) -> float:
    """Fraction of experiments where the confidence sequence ever excluded the true effect."""
    rng = random.Random(seed)
    true_effect = p_treatment - p_control
    misses = 0
    for _ in range(n_sim):
        c_conv = c_n = t_conv = t_n = 0
        missed = False
        for users in range(1, max_n + 1):
            c_n += 1
            if rng.random() < p_control:
                c_conv += 1
            t_n += 1
            if rng.random() < p_treatment:
                t_conv += 1
            if users < step or users % step != 0:
                continue
            rate_c = c_conv / c_n
            rate_t = t_conv / t_n
            variance = rate_c * (1 - rate_c) / c_n + rate_t * (1 - rate_t) / t_n
            if variance <= 0:
                continue
            lower, upper = confidence_sequence(rate_t - rate_c, variance, tau_squared, alpha)
            if not (lower <= true_effect <= upper):
                missed = True
                break
        misses += int(missed)
    return misses / n_sim


def test_confidence_sequence_covers_true_effect_uniformly_over_time() -> None:
    miss_rate = _simulate_coverage(
        p_control=0.20,
        p_treatment=0.26,  # true effect = 0.06
        tau_squared=default_mixture_variance(0.05),
        alpha=0.05,
        n_sim=500,
        max_n=1500,
        step=30,
        seed=42,
    )
    # Anytime coverage: the sequence should drop the true effect on at most alpha of runs even
    # though it is checked at every one of the 50 looks.
    assert miss_rate <= 0.07, f"anytime miss rate exceeds alpha: {miss_rate}"
