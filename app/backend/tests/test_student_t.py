from pathlib import Path
import sys
import math

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.stats.student_t import t_cdf, t_ppf


@pytest.mark.parametrize(
    "value,df,expected",
    [
        # Reference values from scipy.stats.t (cross-checked locally; not committed dep).
        (0.5, 1, 0.6475836177),
        (1.0, 1, 0.7500000000),
        (1.96, 1, 0.8498285541),
        (0.5, 2, 0.6666666667),
        (1.0, 2, 0.7886751346),
        (1.96, 2, 0.9054713452),
        (1.0, 5, 0.8183912662),
        (1.96, 5, 0.9463560237),
        (1.0, 10, 0.8295534338),
        (1.96, 10, 0.9607818799),
        (1.96, 30, 0.9703288436),
        (2.5, 30, 0.9909421755),
    ],
)
def test_t_cdf_matches_reference(value: float, df: int, expected: float) -> None:
    assert t_cdf(value, df) == pytest.approx(expected, abs=1e-7)


def test_t_cdf_is_symmetric_around_zero() -> None:
    for df in (1, 2, 5, 10, 50):
        for x in (0.5, 1.0, 2.5, 5.0):
            assert t_cdf(-x, df) == pytest.approx(1.0 - t_cdf(x, df), abs=1e-9)


def test_t_cdf_falls_back_to_normal_for_large_df() -> None:
    from statistics import NormalDist

    n = NormalDist()
    for x in (-2.0, 0.0, 1.5, 3.0):
        assert t_cdf(x, 1e9) == pytest.approx(n.cdf(x), abs=1e-9)


def test_t_cdf_handles_degenerate_df() -> None:
    from statistics import NormalDist

    n = NormalDist()
    for df in (0, -1, math.inf, math.nan):
        assert t_cdf(1.0, df) == pytest.approx(n.cdf(1.0), abs=1e-9)


@pytest.mark.parametrize(
    "probability,df,expected",
    [
        (0.975, 5, 2.5705818356),
        (0.995, 5, 4.0321429836),
        (0.975, 10, 2.2281388520),
        (0.995, 10, 3.1692726726),
        (0.975, 30, 2.0422724563),
        (0.995, 30, 2.7499956536),
        (0.995, 1, 63.6567411629),
    ],
)
def test_t_ppf_matches_reference(probability: float, df: int, expected: float) -> None:
    assert t_ppf(probability, df) == pytest.approx(expected, abs=1e-4)


def test_t_ppf_inverse_of_t_cdf() -> None:
    for df in (2, 5, 10, 30):
        for p in (0.05, 0.25, 0.5, 0.75, 0.95):
            x = t_ppf(p, df)
            assert t_cdf(x, df) == pytest.approx(p, abs=1e-7)


def test_t_ppf_rejects_invalid_probability() -> None:
    with pytest.raises(ValueError):
        t_ppf(0.0, 10)
    with pytest.raises(ValueError):
        t_ppf(1.0, 10)
    with pytest.raises(ValueError):
        t_ppf(-0.1, 10)
