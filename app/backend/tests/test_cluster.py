"""Unit tests for the cluster design-effect sizing (P5.2).

Numbers are frozen against the literature and Monte Carlo in
``scratchpad/verify_cluster_design_effect.py`` (Kish 1965; Donner & Klar 2000; Hayes & Moulton 2009).
"""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.stats.cluster import cluster_design_effect, inflate_for_cluster_design


@pytest.mark.parametrize(
    ("avg_cluster_size", "icc", "expected"),
    [
        (100, 0.02, 2.98),  # Hayes & Moulton (2009) worked figure
        (20, 0.01, 1.19),
        (50, 0.05, 3.45),  # Donner & Klar style
        (30, 0.03, 1.87),
    ],
)
def test_design_effect_matches_literature(avg_cluster_size: float, icc: float, expected: float) -> None:
    assert cluster_design_effect(avg_cluster_size, icc) == pytest.approx(expected, abs=1e-9)


def test_design_effect_icc_zero_degenerates_to_one() -> None:
    # ICC = 0 -> independent observations -> DEFF = 1 for any cluster size.
    for m in (1, 10, 100, 1000):
        assert cluster_design_effect(m, 0.0) == 1.0


def test_design_effect_single_member_cluster_is_one() -> None:
    # m = 1 -> one individual per "cluster" is not clustering -> DEFF = 1 for any ICC.
    for icc in (0.0, 0.01, 0.2, 0.9, 1.0):
        assert cluster_design_effect(1, icc) == 1.0


def test_design_effect_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        cluster_design_effect(0.5, 0.02)  # cluster size < 1
    with pytest.raises(ValueError):
        cluster_design_effect(100, -0.01)  # icc < 0
    with pytest.raises(ValueError):
        cluster_design_effect(100, 1.01)  # icc > 1


def test_inflate_worked_example_hayes_moulton() -> None:
    # n_ind = 1000, m = 100, ICC = 0.02 -> DEFF 2.98 -> 2980 individuals = 30 clusters of ~100 per arm.
    result = inflate_for_cluster_design(1000, 100, 0.02, variants_count=2)
    assert result["design_effect"] == pytest.approx(2.98, abs=1e-9)
    assert result["sample_size_per_variant"] == 2980
    assert result["total_sample_size"] == 5960
    assert result["clusters_per_variant"] == 30


def test_inflate_worked_example_donner_klar() -> None:
    # n_ind = 500, m = 50, ICC = 0.05 -> DEFF 3.45 -> 1725 = 35 clusters of ~50 per arm.
    result = inflate_for_cluster_design(500, 50, 0.05)
    assert result["design_effect"] == pytest.approx(3.45, abs=1e-9)
    assert result["sample_size_per_variant"] == 1725
    assert result["clusters_per_variant"] == 35


def test_inflate_icc_zero_is_identical_to_individual_path() -> None:
    # The strongest correctness check: ICC = 0 must reproduce the individual-level n exactly.
    result = inflate_for_cluster_design(1000, 100, 0.0)
    assert result["design_effect"] == 1.0
    assert result["sample_size_per_variant"] == 1000
    assert result["total_sample_size"] == 2000
    assert result["clusters_per_variant"] == 10  # ceil(1000 / 100)


def test_inflate_single_member_cluster_is_identical_to_individual_path() -> None:
    result = inflate_for_cluster_design(1000, 1, 0.3)
    assert result["design_effect"] == 1.0
    assert result["sample_size_per_variant"] == 1000
    assert result["clusters_per_variant"] == 1000  # one member per cluster


def test_inflate_three_variants_scales_total() -> None:
    result = inflate_for_cluster_design(1000, 100, 0.02, variants_count=3)
    assert result["sample_size_per_variant"] == 2980
    assert result["total_sample_size"] == 8940  # 2980 * 3


def test_inflate_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        inflate_for_cluster_design(0, 100, 0.02)  # n < 1
    with pytest.raises(ValueError):
        inflate_for_cluster_design(1000, 100, 0.02, variants_count=1)  # < 2 variants
    with pytest.raises(ValueError):
        inflate_for_cluster_design(1000, 0.5, 0.02)  # cluster size < 1
