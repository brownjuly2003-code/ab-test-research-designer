from pathlib import Path
import math
import sys

from hypothesis import assume, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.stats.bayesian import (
    bayesian_sample_size_binary,
    bayesian_sample_size_continuous,
    precision_to_mde_equivalent,
)

FINITE_FLOATS = {"allow_nan": False, "allow_infinity": False}


@settings(max_examples=50, deadline=5000)
@given(
    baseline_rate=st.floats(min_value=0.01, max_value=0.99, **FINITE_FLOATS),
    desired_precision=st.floats(min_value=0.0005, max_value=0.2, **FINITE_FLOATS),
    credibility=st.floats(min_value=0.51, max_value=0.99, **FINITE_FLOATS),
)
def test_bayesian_binary_sample_size_is_positive_and_finite(
    baseline_rate: float,
    desired_precision: float,
    credibility: float,
) -> None:
    sample_size = bayesian_sample_size_binary(baseline_rate, desired_precision, credibility)

    assert sample_size > 0
    assert math.isfinite(sample_size)


@settings(max_examples=50, deadline=5000)
@given(
    std_dev=st.floats(min_value=0.1, max_value=500.0, **FINITE_FLOATS),
    desired_precision=st.floats(min_value=0.1, max_value=100.0, **FINITE_FLOATS),
    credibility=st.floats(min_value=0.51, max_value=0.99, **FINITE_FLOATS),
)
def test_bayesian_continuous_sample_size_is_positive_and_finite(
    std_dev: float,
    desired_precision: float,
    credibility: float,
) -> None:
    sample_size = bayesian_sample_size_continuous(std_dev, desired_precision, credibility)

    assert sample_size > 0
    assert math.isfinite(sample_size)


@settings(max_examples=50, deadline=5000)
@given(
    baseline_rate=st.floats(min_value=0.01, max_value=0.99, **FINITE_FLOATS),
    precision_a=st.floats(min_value=0.0005, max_value=0.2, **FINITE_FLOATS),
    precision_b=st.floats(min_value=0.0005, max_value=0.2, **FINITE_FLOATS),
    credibility=st.floats(min_value=0.51, max_value=0.99, **FINITE_FLOATS),
)
def test_bayesian_binary_sample_size_decreases_as_precision_relaxes(
    baseline_rate: float,
    precision_a: float,
    precision_b: float,
    credibility: float,
) -> None:
    tighter_precision, looser_precision = sorted((precision_a, precision_b))
    assume(tighter_precision < looser_precision)

    tighter = bayesian_sample_size_binary(baseline_rate, tighter_precision, credibility)
    looser = bayesian_sample_size_binary(baseline_rate, looser_precision, credibility)

    assert tighter >= looser


@settings(max_examples=50, deadline=5000)
@given(
    std_dev=st.floats(min_value=0.1, max_value=500.0, **FINITE_FLOATS),
    precision_a=st.floats(min_value=0.1, max_value=100.0, **FINITE_FLOATS),
    precision_b=st.floats(min_value=0.1, max_value=100.0, **FINITE_FLOATS),
    credibility=st.floats(min_value=0.51, max_value=0.99, **FINITE_FLOATS),
)
def test_bayesian_continuous_sample_size_decreases_as_precision_relaxes(
    std_dev: float,
    precision_a: float,
    precision_b: float,
    credibility: float,
) -> None:
    tighter_precision, looser_precision = sorted((precision_a, precision_b))
    assume(tighter_precision < looser_precision)

    tighter = bayesian_sample_size_continuous(std_dev, tighter_precision, credibility)
    looser = bayesian_sample_size_continuous(std_dev, looser_precision, credibility)

    assert tighter >= looser


@settings(max_examples=50, deadline=5000)
@given(
    baseline_rate=st.floats(min_value=0.01, max_value=0.99, **FINITE_FLOATS),
    desired_precision=st.floats(min_value=0.0005, max_value=0.2, **FINITE_FLOATS),
    credibility_a=st.floats(min_value=0.51, max_value=0.99, **FINITE_FLOATS),
    credibility_b=st.floats(min_value=0.51, max_value=0.99, **FINITE_FLOATS),
)
def test_bayesian_binary_sample_size_increases_with_credibility(
    baseline_rate: float,
    desired_precision: float,
    credibility_a: float,
    credibility_b: float,
) -> None:
    lower_credibility, higher_credibility = sorted((credibility_a, credibility_b))
    assume(lower_credibility < higher_credibility)

    lower = bayesian_sample_size_binary(baseline_rate, desired_precision, lower_credibility)
    higher = bayesian_sample_size_binary(baseline_rate, desired_precision, higher_credibility)

    assert lower <= higher


@settings(max_examples=50, deadline=5000)
@given(
    std_dev=st.floats(min_value=0.1, max_value=500.0, **FINITE_FLOATS),
    desired_precision=st.floats(min_value=0.1, max_value=100.0, **FINITE_FLOATS),
    credibility_a=st.floats(min_value=0.51, max_value=0.99, **FINITE_FLOATS),
    credibility_b=st.floats(min_value=0.51, max_value=0.99, **FINITE_FLOATS),
)
def test_bayesian_continuous_sample_size_increases_with_credibility(
    std_dev: float,
    desired_precision: float,
    credibility_a: float,
    credibility_b: float,
) -> None:
    lower_credibility, higher_credibility = sorted((credibility_a, credibility_b))
    assume(lower_credibility < higher_credibility)

    lower = bayesian_sample_size_continuous(std_dev, desired_precision, lower_credibility)
    higher = bayesian_sample_size_continuous(std_dev, desired_precision, higher_credibility)

    assert lower <= higher


@settings(max_examples=50, deadline=5000)
@given(
    baseline_rate=st.floats(min_value=0.01, max_value=0.99, **FINITE_FLOATS),
    desired_precision=st.floats(min_value=0.0005, max_value=0.2, **FINITE_FLOATS),
    credibility=st.floats(min_value=0.51, max_value=0.99, **FINITE_FLOATS),
)
def test_bayesian_binary_sample_size_is_symmetric_around_half_rate(
    baseline_rate: float,
    desired_precision: float,
    credibility: float,
) -> None:
    mirrored_rate = 1 - baseline_rate

    left = bayesian_sample_size_binary(baseline_rate, desired_precision, credibility)
    right = bayesian_sample_size_binary(mirrored_rate, desired_precision, credibility)

    assert left == right


@settings(max_examples=50, deadline=5000)
@given(
    desired_precision=st.floats(min_value=0.0005, max_value=100.0, **FINITE_FLOATS),
    multiplier=st.floats(min_value=0.5, max_value=5.0, **FINITE_FLOATS),
)
def test_precision_to_mde_equivalent_is_linear_in_precision(
    desired_precision: float,
    multiplier: float,
) -> None:
    base = precision_to_mde_equivalent(desired_precision)
    scaled = precision_to_mde_equivalent(desired_precision * multiplier)

    assert base > 0
    assert math.isfinite(base)
    assert math.isclose(scaled, base * multiplier, rel_tol=1e-12, abs_tol=1e-12)
