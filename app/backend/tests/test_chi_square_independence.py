"""Tests for the chi-square test of independence (``stats/chi_square_independence.py``) and its
service / endpoint wiring.

Coverage: the statistic, p-value and Cramér's V against frozen ``scipy.stats.chi2_contingency
(correction=False)`` reference values (scipy is cross-checked locally, not a committed dependency);
an independent recomputation of the chi-square from the definition (no scipy); transpose invariance;
the perfect-independence and strong-association extremes; the low-expected-count (Cochran) warning;
monotonicity of the p-value as the table is scaled up; every degenerate guard (too few rows/columns,
ragged shape, negative counts, empty row/column, zero total, over the cap, bad alpha); a Monte-Carlo
proof of type-I control under the independence null; and the service + HTTP layer (rounding,
localization, 400 on a degenerate table, 422 on a malformed one).
"""

import math
import random

import pytest
from fastapi.testclient import TestClient

from app.backend.app.main import create_app
from app.backend.app.schemas.api import CategoricalResultsRequest
from app.backend.app.services.results_service import analyze_categorical_results
from app.backend.app.stats.chi_square_independence import (
    MAX_CONTINGENCY_TOTAL,
    chi_square_independence_test,
)

# Frozen references from scipy.stats.chi2_contingency(table, correction=False) — the uncorrected
# Pearson statistic. Cross-checked locally at implementation time; scipy is not a committed dependency.
# Each row: (table, chi_square, dof, p_value, cramers_v, n_total, min_expected).
SCIPY_REFERENCE = [
    ([[30, 70], [50, 50]], 8.3333333333, 1, 0.0038924171, 0.2041241452, 200, 40.0),
    ([[10, 20, 30], [30, 20, 10]], 20.0, 2, 0.0000453999, 0.4082482905, 120, 20.0),
    ([[20, 30, 50], [25, 35, 40], [30, 40, 30]], 8.4285714286, 4, 0.0770821454, 0.1185226520, 300, 25.0),
    ([[90, 10], [10, 90]], 128.0, 1, 0.0, 0.8, 200, 50.0),
    ([[1, 2], [3, 1]], 1.2152777778, 1, 0.2702893848, 0.4166666667, 7, 1.2857142857),
]


@pytest.mark.parametrize("table,chi,dof,p,v,n,min_exp", SCIPY_REFERENCE)
def test_matches_scipy_reference(table, chi, dof, p, v, n, min_exp) -> None:
    result = chi_square_independence_test(table)
    assert result["chi_square"] == pytest.approx(chi, abs=1e-6)
    assert result["degrees_of_freedom"] == dof
    assert result["p_value"] == pytest.approx(p, abs=1e-6)
    assert result["cramers_v"] == pytest.approx(v, abs=1e-6)
    assert result["n_total"] == n
    assert result["min_expected_count"] == pytest.approx(min_exp, abs=1e-6)


def test_chi_square_matches_definition_independently() -> None:
    """Recompute the statistic and Cramér's V straight from the textbook definition (no module call
    for the math) and confirm the module agrees."""
    table = [[12, 5, 8], [7, 14, 9], [3, 6, 21]]
    rows = len(table)
    cols = len(table[0])
    row_totals = [sum(r) for r in table]
    col_totals = [sum(table[i][j] for i in range(rows)) for j in range(cols)]
    n = sum(row_totals)
    expected_chi = sum(
        (table[i][j] - row_totals[i] * col_totals[j] / n) ** 2 / (row_totals[i] * col_totals[j] / n)
        for i in range(rows)
        for j in range(cols)
    )
    expected_v = math.sqrt(expected_chi / (n * min(rows - 1, cols - 1)))

    result = chi_square_independence_test(table)
    assert result["chi_square"] == pytest.approx(expected_chi, rel=1e-12)
    assert result["cramers_v"] == pytest.approx(expected_v, rel=1e-12)
    assert result["degrees_of_freedom"] == (rows - 1) * (cols - 1)


def test_transpose_invariance() -> None:
    """Chi-square, df and Cramér's V are invariant under transposing the table (independence is a
    symmetric relationship between the two classifications)."""
    table = [[10, 20, 30], [30, 20, 10]]
    transposed = [[table[i][j] for i in range(len(table))] for j in range(len(table[0]))]
    a = chi_square_independence_test(table)
    b = chi_square_independence_test(transposed)
    assert a["chi_square"] == pytest.approx(b["chi_square"], rel=1e-12)
    assert a["degrees_of_freedom"] == b["degrees_of_freedom"]
    assert a["p_value"] == pytest.approx(b["p_value"], rel=1e-9)
    assert a["cramers_v"] == pytest.approx(b["cramers_v"], rel=1e-12)


def test_perfect_independence_is_zero() -> None:
    result = chi_square_independence_test([[25, 25], [25, 25]])
    assert result["chi_square"] == pytest.approx(0.0, abs=1e-12)
    assert result["p_value"] == pytest.approx(1.0, abs=1e-12)
    assert result["cramers_v"] == pytest.approx(0.0, abs=1e-12)
    assert result["is_significant"] is False


def test_strong_association_cramers_v_near_one() -> None:
    result = chi_square_independence_test([[100, 0], [0, 100]])
    # A perfectly diagonal 2x2 has Cramér's V = 1 (maximal association).
    assert result["cramers_v"] == pytest.approx(1.0, abs=1e-12)
    assert result["is_significant"] is True


def test_cramers_v_always_in_unit_interval() -> None:
    for table, *_ in SCIPY_REFERENCE:
        v = chi_square_independence_test(table)["cramers_v"]
        assert 0.0 <= v <= 1.0


def test_low_expected_warning_flag() -> None:
    # Sparse 2x2: expected counts fall below 5 -> warning.
    assert chi_square_independence_test([[1, 2], [3, 1]])["low_expected_warning"] is True
    # Well-populated table: every expected count is comfortably above 5 -> no warning.
    assert chi_square_independence_test([[30, 70], [50, 50]])["low_expected_warning"] is False


def test_p_value_decreases_as_table_scales_up() -> None:
    """The same association pattern at a larger sample size is more significant (smaller p)."""
    base = [[30, 20], [20, 30]]
    scaled = [[300, 200], [200, 300]]
    p_small = chi_square_independence_test(base)["p_value"]
    p_large = chi_square_independence_test(scaled)["p_value"]
    assert p_large < p_small


def test_is_significant_respects_alpha() -> None:
    table = [[20, 30, 50], [25, 35, 40], [30, 40, 30]]  # p ~ 0.077
    assert chi_square_independence_test(table, alpha=0.10)["is_significant"] is True
    assert chi_square_independence_test(table, alpha=0.05)["is_significant"] is False


# --- degenerate guards -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "table",
    [
        [[0, 0], [5, 5]],  # empty row
        [[5, 0], [5, 0]],  # empty column
    ],
)
def test_empty_row_or_column_raises(table) -> None:
    with pytest.raises(ValueError, match="row and column"):
        chi_square_independence_test(table)


def test_zero_total_raises() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        chi_square_independence_test([[0, 0], [0, 0]])


def test_too_few_rows_raises() -> None:
    with pytest.raises(ValueError, match="two rows"):
        chi_square_independence_test([[1, 2]])


def test_too_few_columns_raises() -> None:
    with pytest.raises(ValueError, match="two columns"):
        chi_square_independence_test([[1], [2]])


def test_ragged_table_raises() -> None:
    with pytest.raises(ValueError, match="rectangular"):
        chi_square_independence_test([[1, 2, 3], [4, 5]])


def test_negative_counts_raise() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        chi_square_independence_test([[1, -2], [3, 4]])


def test_alpha_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="alpha"):
        chi_square_independence_test([[30, 70], [50, 50]], alpha=1.5)


def test_total_over_cap_raises() -> None:
    half = MAX_CONTINGENCY_TOTAL  # each cell at the cap -> total well over it
    with pytest.raises(ValueError, match="cap"):
        chi_square_independence_test([[half, half], [half, half]])


# --- Monte-Carlo type-I control under the independence null -----------------------------------


def test_type_one_error_is_controlled_under_independence() -> None:
    """Under H0 (both groups share the same success probability, so group and outcome are
    independent) the test should reject at roughly alpha, not far above it."""
    rng = random.Random(20240630)
    alpha = 0.05
    trials = 400
    n_per_group = 200
    p_shared = 0.4
    rejections = 0
    for _ in range(trials):
        a = sum(1 for _ in range(n_per_group) if rng.random() < p_shared)
        b = sum(1 for _ in range(n_per_group) if rng.random() < p_shared)
        table = [[a, n_per_group - a], [b, n_per_group - b]]
        if chi_square_independence_test(table, alpha=alpha)["is_significant"]:
            rejections += 1
    rate = rejections / trials
    # Expected ~0.05; with 400 trials a [0.02, 0.10] band is a wide, stable guard.
    assert 0.02 <= rate <= 0.10


# --- service layer ---------------------------------------------------------------------------


def test_service_rounds_and_sets_verdict() -> None:
    response = analyze_categorical_results(
        CategoricalResultsRequest(table=[[10, 20, 30], [30, 20, 10]])
    )
    assert response.degrees_of_freedom == 2
    assert response.num_rows == 2 and response.num_cols == 3
    assert response.n_total == 120
    assert response.is_significant is True
    assert response.verdict == "Association detected"
    assert "Cramér's V" in response.interpretation
    # rounded to 6 dp for the p-value, 4 dp for chi-square / V
    assert response.p_value == pytest.approx(0.000045, abs=1e-6)
    assert response.cramers_v == pytest.approx(0.4082, abs=1e-4)


def test_service_degenerate_raises_value_error() -> None:
    with pytest.raises(ValueError):
        analyze_categorical_results(CategoricalResultsRequest(table=[[0, 0], [5, 5]]))


# --- HTTP endpoint ---------------------------------------------------------------------------


def test_endpoint_significant() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/results/categorical",
        json={"table": [[90, 10], [10, 90]], "alpha": 0.05},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_significant"] is True
    assert body["degrees_of_freedom"] == 1
    assert body["cramers_v"] == pytest.approx(0.8, abs=1e-4)
    assert body["low_expected_warning"] is False


def test_endpoint_not_significant() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/results/categorical",
        json={"table": [[25, 25], [25, 25]]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_significant"] is False
    assert body["p_value"] == pytest.approx(1.0, abs=1e-6)


def test_endpoint_localizes_via_accept_language() -> None:
    client = TestClient(create_app())
    body = {"table": [[10, 20, 30], [30, 20, 10]]}
    english = client.post("/api/v1/results/categorical", json=body)
    russian = client.post("/api/v1/results/categorical", json=body, headers={"Accept-Language": "ru"})
    assert english.status_code == 200 and russian.status_code == 200
    en, ru = english.json(), russian.json()
    assert en["verdict"] == "Association detected"
    assert ru["verdict"] != en["verdict"]
    assert "Связь" in ru["verdict"]
    # Numbers are language-independent.
    assert ru["chi_square"] == en["chi_square"]
    assert ru["p_value"] == en["p_value"]
    assert ru["cramers_v"] == en["cramers_v"]


def test_endpoint_low_expected_warning() -> None:
    client = TestClient(create_app())
    response = client.post("/api/v1/results/categorical", json={"table": [[1, 2], [3, 1]]})
    assert response.status_code == 200
    assert response.json()["low_expected_warning"] is True


def test_endpoint_ragged_table_returns_422() -> None:
    client = TestClient(create_app())
    response = client.post("/api/v1/results/categorical", json={"table": [[1, 2, 3], [4, 5]]})
    assert response.status_code == 422


def test_endpoint_empty_row_returns_400() -> None:
    """A structurally valid but statistically degenerate table (empty row) is a ValueError from the
    stats layer, which the global handler maps to 400, not 422."""
    client = TestClient(create_app())
    response = client.post("/api/v1/results/categorical", json={"table": [[0, 0], [5, 5]]})
    assert response.status_code == 400


def test_endpoint_too_many_rows_returns_422() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/results/categorical",
        json={"table": [[1, 1] for _ in range(60)]},  # exceeds the dimension cap
    )
    assert response.status_code == 422
