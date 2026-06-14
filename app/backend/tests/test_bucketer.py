from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.execution.bucketer import (
    assign_variation,
    choose_variation,
    fnv32a,
    get_bucket_ranges,
    hash_to_unit,
    in_namespace,
    preview_assignment_distribution,
)

# Canonical FNV-1a 32-bit reference values (Landon Curt Noll's test suite).
FNV_REFERENCE = {
    "": 0x811C9DC5,
    "a": 0xE40C292C,
    "ab": 0x4D2505CA,
    "foobar": 0xBF9CF968,
}

# Verbatim from growthbook/packages/sdk-js/test/cases.json — [seed, value, version, expected].
GROWTHBOOK_HASH_VECTORS = [
    ("", "a", 1, 0.22),
    ("", "b", 1, 0.077),
    ("b", "a", 1, 0.946),
    ("ef", "d", 1, 0.652),
    ("asdf", "8952klfjas09ujk", 1, 0.549),
    ("", "123", 1, 0.011),
    ("", '___)((*":&', 1, 0.563),
    ("seed", "a", 2, 0.0505),
    ("seed", "b", 2, 0.2696),
    ("foo", "ab", 2, 0.2575),
    ("foo", "def", 2, 0.2019),
    ("89123klj", "8952klfjas09ujkasdf", 2, 0.124),
    ("90850943850283058242805", "123", 2, 0.7516),
    ("()**(%$##$%#$#", '___)((*":&', 2, 0.0128),
]

# Verbatim getBucketRange cases — [numVariations, coverage, weights] -> expected ranges.
GROWTHBOOK_BUCKET_RANGE_VECTORS = [
    ((2, 1, None), [(0, 0.5), (0.5, 1)]),
    ((2, 0.5, None), [(0, 0.25), (0.5, 0.75)]),
    ((2, 0, None), [(0, 0), (0.5, 0.5)]),
    ((4, 1, None), [(0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1)]),
    ((2, 1, [0.4, 0.6]), [(0, 0.4), (0.4, 1)]),
    ((3, 1, [0.2, 0.3, 0.5]), [(0, 0.2), (0.2, 0.5), (0.5, 1)]),
    ((3, 0.2, [0.2, 0.3, 0.5]), [(0, 0.04), (0.2, 0.26), (0.5, 0.6)]),
    ((2, -0.2, None), [(0, 0), (0.5, 0.5)]),
    ((2, 1.5, None), [(0, 0.5), (0.5, 1)]),
    ((2, 1, [0.4, 0.1]), [(0, 0.5), (0.5, 1)]),
    ((2, 1, [0.7, 0.6]), [(0, 0.5), (0.5, 1)]),
    ((4, 1, [0.4, 0.4, 0.2]), [(0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1)]),
    ((2, 1, [0.4, 0.5999]), [(0, 0.4), (0.4, 0.9999)]),
]


@pytest.mark.parametrize("text, expected", FNV_REFERENCE.items())
def test_fnv32a_matches_canonical_reference(text: str, expected: int) -> None:
    assert fnv32a(text) == expected


@pytest.mark.parametrize("seed, value, version, expected", GROWTHBOOK_HASH_VECTORS)
def test_hash_to_unit_matches_growthbook_vectors(seed: str, value: str, version: int, expected: float) -> None:
    assert hash_to_unit(seed, value, version) == pytest.approx(expected, abs=1e-9)


def test_hash_to_unit_returns_none_for_unknown_version() -> None:
    assert hash_to_unit("abc", "def", 99) is None


@pytest.mark.parametrize("args, expected", GROWTHBOOK_BUCKET_RANGE_VECTORS)
def test_get_bucket_ranges_matches_growthbook_vectors(args, expected) -> None:
    num_variations, coverage, weights = args
    ranges = get_bucket_ranges(num_variations, coverage, weights)
    assert len(ranges) == len(expected)
    for (lo, hi), (expected_lo, expected_hi) in zip(ranges, expected, strict=True):
        assert lo == pytest.approx(expected_lo, abs=1e-9)
        assert hi == pytest.approx(expected_hi, abs=1e-9)


def test_choose_variation_uses_half_open_ranges() -> None:
    ranges = [(0.0, 0.5), (0.5, 1.0)]
    assert choose_variation(0.0, ranges) == 0
    assert choose_variation(0.4999, ranges) == 0
    assert choose_variation(0.5, ranges) == 1
    assert choose_variation(0.999, ranges) == 1


def test_choose_variation_returns_minus_one_outside_coverage() -> None:
    ranges = [(0.0, 0.25), (0.5, 0.75)]  # coverage 0.5
    assert choose_variation(0.3, ranges) == -1
    assert choose_variation(0.9, ranges) == -1


def test_assign_variation_is_deterministic_and_sticky() -> None:
    first = assign_variation("exp-seed", "user-42", num_variations=2)
    second = assign_variation("exp-seed", "user-42", num_variations=2)
    assert first == second
    assert first["in_experiment"] is True
    assert first["variation_index"] in (0, 1)


def test_assign_variation_distribution_is_balanced_for_equal_weights() -> None:
    counts = [0, 0]
    sample_size = 5000
    for index in range(sample_size):
        result = assign_variation("balanced-seed", f"user-{index}", num_variations=2)
        counts[result["variation_index"]] += 1

    assert sum(counts) == sample_size
    for count in counts:
        assert 0.45 <= count / sample_size <= 0.55


def test_assign_variation_coverage_controls_in_experiment_fraction() -> None:
    in_experiment = 0
    sample_size = 5000
    for index in range(sample_size):
        result = assign_variation("ramp-seed", f"user-{index}", num_variations=2, coverage=0.4)
        if result["in_experiment"]:
            in_experiment += 1

    assert 0.35 <= in_experiment / sample_size <= 0.45


def test_assign_variation_respects_uneven_weights() -> None:
    counts = [0, 0]
    sample_size = 6000
    for index in range(sample_size):
        result = assign_variation("weighted-seed", f"user-{index}", num_variations=2, weights=[0.2, 0.8])
        counts[result["variation_index"]] += 1

    assert counts[1] / sample_size > counts[0] / sample_size
    assert 0.15 <= counts[0] / sample_size <= 0.25


def test_preview_distribution_is_deterministic_and_complete() -> None:
    first = preview_assignment_distribution("preview-seed", num_variations=2, sample_size=1000)
    second = preview_assignment_distribution("preview-seed", num_variations=2, sample_size=1000)

    assert first == second
    assert first["sample_size"] == 1000
    assert sum(bucket["count"] for bucket in first["distribution"]) == 1000
    assert sum(bucket["fraction"] for bucket in first["distribution"]) == pytest.approx(1.0)
    assert first["in_experiment_fraction"] == pytest.approx(1.0)
    assert len(first["sample_assignments"]) == 25


def test_preview_distribution_reports_unassigned_tail_under_partial_coverage() -> None:
    result = preview_assignment_distribution("ramp-seed", num_variations=2, coverage=0.5, sample_size=2000)

    variation_indices = {bucket["variation_index"] for bucket in result["distribution"]}
    assert -1 in variation_indices  # the unassigned tail is surfaced explicitly
    assert 0.45 <= result["in_experiment_fraction"] <= 0.55


def test_in_namespace_is_deterministic() -> None:
    first = in_namespace("user-1", "checkout", 0.0, 0.5)
    second = in_namespace("user-1", "checkout", 0.0, 0.5)
    assert first == second


def test_in_namespace_membership_fraction_matches_range_width() -> None:
    inside = sum(1 for index in range(5000) if in_namespace(f"u-{index}", "ns", 0.0, 0.3))
    assert 0.27 <= inside / 5000 <= 0.33  # ~30% of users fall in a [0, 0.3) slot


def test_in_namespace_disjoint_slots_never_share_a_user() -> None:
    for index in range(5000):
        user = f"u-{index}"
        in_first = in_namespace(user, "layer", 0.0, 0.5)
        in_second = in_namespace(user, "layer", 0.5, 1.0)
        assert not (in_first and in_second)  # disjoint ranges are mutually exclusive
