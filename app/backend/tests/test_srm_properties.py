from pathlib import Path
import math
import sys

from hypothesis import assume, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.stats.srm import chi_square_srm

FINITE_FLOATS = {"allow_nan": False, "allow_infinity": False}


@st.composite
def exact_srm_case(draw: st.DrawFn) -> tuple[list[int], list[float]]:
    weights = draw(st.lists(st.integers(min_value=1, max_value=8), min_size=2, max_size=8))
    multiplier = draw(st.integers(min_value=1, max_value=2_000))
    total_weight = sum(weights)
    return [weight * multiplier for weight in weights], [weight / total_weight for weight in weights]


@st.composite
def arbitrary_srm_case(draw: st.DrawFn) -> tuple[list[int], list[float]]:
    observed_counts = draw(st.lists(st.integers(min_value=1, max_value=20_000), min_size=2, max_size=8))
    expected_weights = draw(
        st.lists(st.integers(min_value=1, max_value=20_000), min_size=len(observed_counts), max_size=len(observed_counts))
    )
    total_weight = sum(expected_weights)
    return observed_counts, [weight / total_weight for weight in expected_weights]


@settings(max_examples=50, deadline=5000)
@given(case=exact_srm_case())
def test_srm_exact_expected_counts_have_near_zero_statistic(case: tuple[list[int], list[float]]) -> None:
    observed_counts, expected_fractions = case

    chi_square, p_value, is_srm = chi_square_srm(observed_counts, expected_fractions)

    assert math.isclose(chi_square, 0.0, abs_tol=1e-9)
    assert p_value > 0.95
    assert is_srm is False


@settings(max_examples=50, deadline=5000)
@given(case=exact_srm_case())
def test_srm_single_user_perturbation_does_not_flag_large_balanced_samples(
    case: tuple[list[int], list[float]],
) -> None:
    observed_counts, expected_fractions = case
    assume(len(observed_counts) >= 2)
    assume(observed_counts[1] > 1)

    perturbed_counts = observed_counts.copy()
    perturbed_counts[0] += 1
    perturbed_counts[1] -= 1

    chi_square, p_value, is_srm = chi_square_srm(perturbed_counts, expected_fractions)

    assert math.isfinite(chi_square)
    assert p_value > 0.001
    assert is_srm is False


@settings(max_examples=50, deadline=5000)
@given(case=arbitrary_srm_case())
def test_srm_outputs_are_finite_and_bounded(case: tuple[list[int], list[float]]) -> None:
    observed_counts, expected_fractions = case

    chi_square, p_value, is_srm = chi_square_srm(observed_counts, expected_fractions)

    assert chi_square >= 0
    assert math.isfinite(chi_square)
    assert 0.0 <= p_value <= 1.0
    assert isinstance(is_srm, bool)


@settings(max_examples=50, deadline=5000)
@given(case=arbitrary_srm_case(), rotation=st.integers(min_value=0, max_value=7))
def test_srm_is_invariant_to_joint_rotation(
    case: tuple[list[int], list[float]],
    rotation: int,
) -> None:
    observed_counts, expected_fractions = case
    if observed_counts:
        shift = rotation % len(observed_counts)
    else:
        shift = 0

    rotated_counts = observed_counts[shift:] + observed_counts[:shift]
    rotated_fractions = expected_fractions[shift:] + expected_fractions[:shift]

    original = chi_square_srm(observed_counts, expected_fractions)
    rotated = chi_square_srm(rotated_counts, rotated_fractions)

    assert math.isclose(original[0], rotated[0], rel_tol=0.0, abs_tol=1e-9)
    assert math.isclose(original[1], rotated[1], rel_tol=0.0, abs_tol=1e-9)
    assert original[2] == rotated[2]


@settings(max_examples=50, deadline=5000)
@given(case=arbitrary_srm_case())
def test_srm_expected_counts_preserve_total_sample_size(case: tuple[list[int], list[float]]) -> None:
    observed_counts, expected_fractions = case
    total_observed = sum(observed_counts)
    expected_counts = [fraction * total_observed for fraction in expected_fractions]

    assert math.isclose(sum(expected_counts), total_observed, rel_tol=0.0, abs_tol=1e-6)


@settings(max_examples=50, deadline=5000)
@given(
    total_per_variant=st.integers(min_value=100, max_value=50_000),
    skew_a=st.integers(min_value=1, max_value=1_000),
    skew_b=st.integers(min_value=1, max_value=1_000),
)
def test_srm_larger_skew_increases_chi_square_and_lowers_p_value(
    total_per_variant: int,
    skew_a: int,
    skew_b: int,
) -> None:
    small_skew, large_skew = sorted((skew_a, skew_b))
    assume(small_skew < large_skew < total_per_variant)

    mild = chi_square_srm(
        [total_per_variant - small_skew, total_per_variant + small_skew],
        [0.5, 0.5],
    )
    severe = chi_square_srm(
        [total_per_variant - large_skew, total_per_variant + large_skew],
        [0.5, 0.5],
    )

    assert mild[0] <= severe[0]
    assert mild[1] >= severe[1]
