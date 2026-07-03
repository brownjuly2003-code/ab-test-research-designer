"""Tests for the omnibus analyzers (``stats/omnibus.py``) and their service / endpoint wiring.

Coverage: the Welch one-way ANOVA F / denominator df against frozen ``statsmodels.stats.oneway.
anova_oneway(use_var="unequal")`` reference values and the Kruskal–Wallis H / p against
``scipy.stats.kruskal`` (cross-checked locally via scratchpad ``verify_omnibus_vs_scipy.py``, not
committed dependencies, so the constants are frozen to keep the suite stdlib-only and CI-safe); the
``student_t.f_sf`` F-distribution survival against ``scipy.stats.f.sf``; the tie-corrected
Kruskal–Wallis path; the degenerate guards (a group with zero within-group variance for Welch, a
group of one, all-observations-tied for Kruskal–Wallis); and the service + HTTP layer (rounding,
localization, 400 on a degenerate input, 422 on a malformed one — too few groups, a group with fewer
than two values).
"""

import pytest
from fastapi.testclient import TestClient

from app.backend.app.main import create_app
from app.backend.app.schemas.api import OmnibusResultsRequest
from app.backend.app.services.results_service import analyze_omnibus_results
from app.backend.app.stats.omnibus import kruskal_wallis_test, welch_anova_test
from app.backend.app.stats.student_t import f_sf

# Three unbalanced, heteroscedastic arms (see the scratchpad verification for the frozen numbers).
G1 = [5.1, 4.8, 6.2, 5.5, 4.9, 5.7, 6.0, 5.3]
G2 = [6.5, 7.1, 6.8, 7.4, 6.9, 7.7, 6.2, 7.0, 7.3]
G3 = [5.9, 6.3, 6.7, 5.5, 6.1, 6.4, 7.2]
GROUPS = [G1, G2, G3]


# --- Welch's ANOVA ---------------------------------------------------------------------------


def test_welch_anova_matches_statsmodels() -> None:
    result = welch_anova_test(GROUPS)
    assert result is not None
    # statsmodels anova_oneway(use_var="unequal", welch_correction=True) on the same data.
    assert result["test_statistic"] == pytest.approx(20.6233997113, abs=1e-9)
    assert result["p_value"] == pytest.approx(0.0000860564, abs=1e-9)
    assert result["df_numerator"] == 2.0
    assert result["df_denominator"] == pytest.approx(13.2250716024, abs=1e-7)
    # Descriptive eta squared (SS_between / SS_total on the raw data).
    assert result["effect_size"] == pytest.approx(0.6577832702, abs=1e-9)
    assert result["num_groups"] == 3
    assert result["n_total"] == 24
    assert [s["n"] for s in result["group_summaries"]] == [8, 9, 7]
    assert result["group_summaries"][0]["mean"] == pytest.approx(5.4375, abs=1e-9)


def test_welch_anova_zero_within_group_variance_returns_none() -> None:
    # A group whose values are all identical has zero variance ⇒ its weight n/s² is infinite.
    assert welch_anova_test([[5.0, 5.0, 5.0], [6.0, 7.0, 8.0]]) is None


def test_welch_anova_group_of_one_returns_none() -> None:
    assert welch_anova_test([[5.0], [6.0, 7.0, 8.0]]) is None


def test_welch_anova_requires_two_groups() -> None:
    with pytest.raises(ValueError):
        welch_anova_test([[1.0, 2.0, 3.0]])


def test_welch_anova_rejects_non_finite() -> None:
    with pytest.raises(ValueError):
        welch_anova_test([[1.0, 2.0], [3.0, float("nan")]])


# --- Kruskal–Wallis --------------------------------------------------------------------------


def test_kruskal_wallis_matches_scipy() -> None:
    result = kruskal_wallis_test(GROUPS)
    assert result is not None
    # scipy.stats.kruskal(G1, G2, G3): H = 15.3558529..., p = 0.0004629338.
    assert result["test_statistic"] == pytest.approx(15.3558529156, abs=1e-9)
    assert result["p_value"] == pytest.approx(0.0004629338, abs=1e-9)
    assert result["df_numerator"] == 2.0
    # ε² = H / (N − 1).
    assert result["effect_size"] == pytest.approx(0.6676457789, abs=1e-9)
    mean_ranks = [s["mean_rank"] for s in result["group_summaries"]]
    assert mean_ranks == pytest.approx([5.375, 18.833333333, 12.5], abs=1e-6)


def test_kruskal_wallis_tie_correction_matches_scipy() -> None:
    tie_groups = [[1.0, 2.0, 2.0, 3.0], [2.0, 3.0, 3.0, 4.0], [3.0, 3.0, 4.0, 5.0]]
    result = kruskal_wallis_test(tie_groups)
    assert result is not None
    # scipy.stats.kruskal on the tied data: H = 5.4051724..., p = 0.0670319299 (tie-corrected).
    assert result["test_statistic"] == pytest.approx(5.4051724138, abs=1e-9)
    assert result["p_value"] == pytest.approx(0.0670319299, abs=1e-9)
    assert result["effect_size"] == pytest.approx(0.4913793103, abs=1e-9)


def test_kruskal_wallis_all_tied_returns_none() -> None:
    # No rank variation ⇒ the tie correction collapses to zero, H is undefined.
    assert kruskal_wallis_test([[3.0, 3.0, 3.0], [3.0, 3.0, 3.0]]) is None


def test_kruskal_wallis_requires_two_groups() -> None:
    with pytest.raises(ValueError):
        kruskal_wallis_test([[1.0, 2.0, 3.0]])


# --- F-distribution survival -----------------------------------------------------------------


def test_f_sf_matches_scipy() -> None:
    # scipy.stats.f.sf reference values. Tolerance 1e-7 matches the incomplete-beta continued-fraction
    # convergence (_BETACF_EPS = 3e-7); the fractional-df case sits ~1e-9 off scipy's value.
    assert f_sf(5.0, 2, 10) == pytest.approx(0.03125, abs=1e-7)
    assert f_sf(0.5, 2, 8.0) == pytest.approx(0.6242950770, abs=1e-7)
    assert f_sf(1.0, 3, 3.5) == pytest.approx(0.4883109229, abs=1e-7)
    assert f_sf(10.0, 4, 20.0) == pytest.approx(0.0001298357, abs=1e-7)
    # A non-positive F sits below the whole distribution.
    assert f_sf(0.0, 2, 10) == 1.0
    assert f_sf(-3.0, 2, 10) == 1.0


def test_f_sf_rejects_bad_degrees_of_freedom() -> None:
    with pytest.raises(ValueError):
        f_sf(2.0, 0, 10)


# --- service layer ---------------------------------------------------------------------------


def test_service_welch_rounds_and_sets_verdict() -> None:
    response = analyze_omnibus_results(
        OmnibusResultsRequest(test_type="welch_anova", groups=GROUPS)
    )
    assert response.test_type == "welch_anova"
    assert response.test_statistic == 20.6234  # rounded to 4 dp
    assert response.df_numerator == 2.0
    assert response.df_denominator == 13.2251
    assert response.p_value == 0.000086  # rounded to 6 dp
    assert response.effect_size == 0.6578
    assert response.is_significant is True
    assert response.num_groups == 3
    assert response.n_total == 24
    assert "η²" in response.effect_size_label
    assert response.group_summaries[1].mean == 6.9889
    assert response.group_summaries[0].median is None  # Welch path leaves rank fields empty


def test_service_kruskal_sets_rank_summary() -> None:
    response = analyze_omnibus_results(
        OmnibusResultsRequest(test_type="kruskal_wallis", groups=GROUPS)
    )
    assert response.test_type == "kruskal_wallis"
    assert response.test_statistic == 15.3559
    assert response.df_denominator is None  # chi-square referred, no denominator df
    assert response.effect_size == 0.6676
    assert response.group_summaries[1].mean_rank == 18.8333
    assert response.group_summaries[0].mean is None  # rank path leaves mean/std empty


def test_service_degenerate_welch_raises() -> None:
    with pytest.raises(ValueError):
        analyze_omnibus_results(
            OmnibusResultsRequest(test_type="welch_anova", groups=[[5.0, 5.0, 5.0], [6.0, 7.0, 8.0]])
        )


# --- HTTP endpoint ---------------------------------------------------------------------------


def test_endpoint_welch_round_trip() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/results/omnibus",
        json={"test_type": "welch_anova", "groups": GROUPS, "alpha": 0.05},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["test_type"] == "welch_anova"
    assert body["p_value"] == 0.000086
    assert body["is_significant"] is True
    assert body["df_denominator"] == 13.2251
    assert len(body["group_summaries"]) == 3


def test_endpoint_kruskal_round_trip() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/results/omnibus",
        json={"test_type": "kruskal_wallis", "groups": GROUPS},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["test_type"] == "kruskal_wallis"
    assert body["test_statistic"] == 15.3559
    assert body["df_denominator"] is None
    assert body["p_value"] == 0.000463


def test_endpoint_localizes_via_accept_language() -> None:
    client = TestClient(create_app())
    payload = {"test_type": "welch_anova", "groups": GROUPS}
    english = client.post("/api/v1/results/omnibus", json=payload)
    russian = client.post("/api/v1/results/omnibus", json=payload, headers={"Accept-Language": "ru"})
    assert english.status_code == 200 and russian.status_code == 200
    en, ru = english.json(), russian.json()
    assert ru["verdict"] != en["verdict"]
    # Numbers are language-independent.
    assert ru["test_statistic"] == en["test_statistic"]
    assert ru["p_value"] == en["p_value"]


def test_endpoint_group_with_one_value_returns_422() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/results/omnibus",
        json={"test_type": "welch_anova", "groups": [[1.0, 2.0], [3.0]]},
    )
    assert response.status_code == 422


def test_endpoint_single_group_returns_422() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/results/omnibus",
        json={"test_type": "kruskal_wallis", "groups": [[1.0, 2.0, 3.0]]},
    )
    assert response.status_code == 422


def test_endpoint_degenerate_welch_returns_400() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/results/omnibus",
        json={"test_type": "welch_anova", "groups": [[5.0, 5.0, 5.0], [6.0, 7.0, 8.0]]},
    )
    assert response.status_code == 400
