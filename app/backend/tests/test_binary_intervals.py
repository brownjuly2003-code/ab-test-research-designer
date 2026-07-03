"""Tests for the Wilson score and Newcombe difference confidence intervals (``stats/binary.py``).

The expected constants are frozen from an independent oracle run (scratchpad
``verify_wilson_newcombe_midp.py``): ``statsmodels.stats.proportion.proportion_confint(method="wilson")``
for the single-proportion interval and ``confint_proportions_2indep(method="newcomb", compare="diff")``
for the difference. statsmodels is cross-checked locally, not a project dependency, so the numbers are
inlined to keep the suite stdlib-only. The 56/70 vs 48/80 difference also reproduces the published 95 %
interval in Newcombe (1998) / Altman "Statistics with Confidence".
"""

import pytest

from app.backend.app.stats.binary import (
    newcombe_difference_interval,
    wilson_score_interval,
)

# --- Wilson score interval (single proportion), 95% -----------------------------------------

_WILSON_95 = {
    (48, 80): (0.4904546501, 0.7003817240),
    (0, 20): (0.0, 0.1611251581),
    (1, 100): (0.0017674321, 0.0544861962),
    (531, 1000): (0.5000102484, 0.5617524926),
    (81, 263): (0.2552885199, 0.3662095770),  # Newcombe (1998) worked-example proportion
}


@pytest.mark.parametrize(("successes", "n", "expected"), [(*k, v) for k, v in _WILSON_95.items()])
def test_wilson_matches_statsmodels(successes: int, n: int, expected: tuple[float, float]) -> None:
    lower, upper = wilson_score_interval(successes, n, 0.05)
    assert lower == pytest.approx(expected[0], abs=1e-9)
    assert upper == pytest.approx(expected[1], abs=1e-9)


def test_wilson_stays_inside_unit_interval_at_the_boundaries() -> None:
    # Where the Wald interval degenerates to a point at p̂ ∈ {0, 1}, Wilson gives a real interval.
    lo0, hi0 = wilson_score_interval(0, 30, 0.05)
    lo1, hi1 = wilson_score_interval(30, 30, 0.05)
    assert lo0 == pytest.approx(0.0, abs=1e-12)
    assert 0.0 < hi0 < 1.0
    assert hi1 == pytest.approx(1.0, abs=1e-12)
    assert 0.0 < lo1 < 1.0


def test_wilson_is_centred_below_phat_for_high_rates() -> None:
    # The score interval pulls toward 1/2, so its centre sits below p̂ when p̂ > 1/2.
    lower, upper = wilson_score_interval(90, 100, 0.05)
    assert (lower + upper) / 2 < 0.90


def test_wilson_narrows_as_n_grows() -> None:
    small = wilson_score_interval(30, 100, 0.05)
    large = wilson_score_interval(300, 1000, 0.05)
    assert (large[1] - large[0]) < (small[1] - small[0])


def test_wilson_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        wilson_score_interval(5, 0, 0.05)
    with pytest.raises(ValueError):
        wilson_score_interval(11, 10, 0.05)
    with pytest.raises(ValueError):
        wilson_score_interval(3, 10, 1.5)


# --- Newcombe hybrid-score interval for the difference p1 - p2, 95% --------------------------

_NEWCOMBE_95 = {
    (56, 70, 48, 80): (0.0524314724, 0.3338726540),  # Altman "Statistics with Confidence" 0.8 vs 0.6
    (63, 93, 45, 86): (0.0108299583, 0.2895403591),
    (10, 10, 0, 10): (0.6075093504, 1.0000000000),  # boundary: 100% vs 0%
    (100, 1000, 130, 1000): (-0.0580704850, -0.0020023487),
}


@pytest.mark.parametrize(
    ("s1", "n1", "s2", "n2", "expected"),
    [(*k, v) for k, v in _NEWCOMBE_95.items()],
)
def test_newcombe_matches_statsmodels(
    s1: int, n1: int, s2: int, n2: int, expected: tuple[float, float]
) -> None:
    lower, upper = newcombe_difference_interval(s1, n1, s2, n2, 0.05)
    assert lower == pytest.approx(expected[0], abs=1e-9)
    assert upper == pytest.approx(expected[1], abs=1e-9)


def test_newcombe_is_antisymmetric_under_group_swap() -> None:
    forward = newcombe_difference_interval(56, 70, 48, 80, 0.05)
    reverse = newcombe_difference_interval(48, 80, 56, 70, 0.05)
    assert reverse[0] == pytest.approx(-forward[1], abs=1e-12)
    assert reverse[1] == pytest.approx(-forward[0], abs=1e-12)


def test_newcombe_brackets_the_point_difference() -> None:
    p1, p2 = 63 / 93, 45 / 86
    lower, upper = newcombe_difference_interval(63, 93, 45, 86, 0.05)
    assert lower < (p1 - p2) < upper


def test_newcombe_stays_within_plus_minus_one() -> None:
    lower, upper = newcombe_difference_interval(50, 50, 0, 50, 0.05)
    assert -1.0 <= lower <= upper <= 1.0
