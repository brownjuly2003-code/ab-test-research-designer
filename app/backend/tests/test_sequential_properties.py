from pathlib import Path
import math
import sys

from hypothesis import assume, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.stats.binary import calculate_binary_sample_size, normal_ppf, standard_normal_cdf
from app.backend.app.stats.sequential import (
    obrien_fleming_boundaries,
    sequential_sample_size_inflation,
)

FINITE_FLOATS = {"allow_nan": False, "allow_infinity": False}


@settings(max_examples=50, deadline=5000)
@given(
    n_looks=st.integers(min_value=1, max_value=10),
    alpha=st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS),
)
def test_sequential_cumulative_alpha_is_monotone_and_bounded(n_looks: int, alpha: float) -> None:
    boundaries = obrien_fleming_boundaries(n_looks, alpha)
    cumulative = [entry["cumulative_alpha_spent"] for entry in boundaries]
    incremental = [entry["incremental_alpha"] for entry in boundaries]

    assert all(value >= 0 for value in incremental)
    assert all(left <= right for left, right in zip(cumulative, cumulative[1:]))
    assert cumulative[-1] <= alpha + 1e-6


@settings(max_examples=50, deadline=5000)
@given(
    n_looks=st.integers(min_value=2, max_value=10),
    alpha=st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS),
)
def test_sequential_z_boundaries_decrease_across_looks(n_looks: int, alpha: float) -> None:
    z_values = [entry["z_boundary"] for entry in obrien_fleming_boundaries(n_looks, alpha)]

    assert all(left >= right for left, right in zip(z_values, z_values[1:]))


@settings(max_examples=50, deadline=5000)
@given(
    n_looks=st.integers(min_value=1, max_value=10),
    alpha=st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS),
)
def test_sequential_two_sided_boundaries_match_reported_p_values(n_looks: int, alpha: float) -> None:
    for entry in obrien_fleming_boundaries(n_looks, alpha):
        expected_p_value = 2 * (1 - standard_normal_cdf(entry["z_boundary"]))

        assert entry["z_boundary"] > 0
        assert math.isclose(expected_p_value, entry["p_boundary"], rel_tol=0.0, abs_tol=5e-4)


@settings(max_examples=50, deadline=5000)
@given(
    n_looks=st.integers(min_value=1, max_value=10),
    alpha=st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS),
)
def test_sequential_final_boundary_is_not_below_fixed_horizon(n_looks: int, alpha: float) -> None:
    fixed_horizon_z = normal_ppf(1 - alpha / 2)
    final_boundary = obrien_fleming_boundaries(n_looks, alpha)[-1]["z_boundary"]

    assert final_boundary + 1e-4 >= fixed_horizon_z


@settings(max_examples=50, deadline=5000)
@given(
    looks_a=st.integers(min_value=1, max_value=10),
    looks_b=st.integers(min_value=1, max_value=10),
    alpha=st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS),
    power=st.floats(min_value=0.5, max_value=0.99, **FINITE_FLOATS),
)
def test_sequential_inflation_is_monotone_in_number_of_looks(
    looks_a: int,
    looks_b: int,
    alpha: float,
    power: float,
) -> None:
    fewer_looks, more_looks = sorted((looks_a, looks_b))
    assume(fewer_looks < more_looks)

    lower_inflation = sequential_sample_size_inflation(fewer_looks, alpha=alpha, power=power)
    higher_inflation = sequential_sample_size_inflation(more_looks, alpha=alpha, power=power)

    assert lower_inflation >= 1.0
    assert lower_inflation <= higher_inflation


@settings(max_examples=50, deadline=5000)
@given(
    baseline_rate=st.floats(min_value=0.01, max_value=0.99, **FINITE_FLOATS),
    mde_pct=st.floats(min_value=0.5, max_value=50.0, **FINITE_FLOATS),
    alpha=st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS),
    power=st.floats(min_value=0.5, max_value=0.99, **FINITE_FLOATS),
    n_looks=st.integers(min_value=2, max_value=10),
)
def test_sequential_adjusted_sample_size_is_not_smaller_than_fixed_horizon(
    baseline_rate: float,
    mde_pct: float,
    alpha: float,
    power: float,
    n_looks: int,
) -> None:
    assume(baseline_rate * (1 + mde_pct / 100) < 1)

    fixed_horizon = calculate_binary_sample_size(baseline_rate, mde_pct, alpha, power)
    adjusted = math.ceil(
        fixed_horizon["sample_size_per_variant"] * sequential_sample_size_inflation(n_looks, alpha, power)
    )

    assert adjusted >= fixed_horizon["sample_size_per_variant"]
