"""Tests for the paired-family analyzers (``stats/paired.py``) and their service / endpoint wiring.

Coverage: the paired t, Wilcoxon signed-rank and McNemar statistics against frozen scipy 1.17.1 /
statsmodels 0.14.6 reference values (cross-checked locally via scratchpad ``verify_paired_vs_scipy.py``,
not committed dependencies, so the constants are frozen to keep the suite stdlib-only and CI-safe);
the audit's flagged edge cases — Wilcoxon zero differences and ties in ``|d|``, McNemar's exact vs
continuity-corrected chi-square branches, the discordance odds ratio when ``c = 0`` and no discordant
pairs at all; the degenerate guards (fewer than two usable pairs, zero difference variance, all
non-zero differences tied); and the service + HTTP layer (rounding, localization, 400 on a degenerate
paired input, 422 on a malformed one — length mismatch, non-binary McNemar values).
"""

import pytest
from fastapi.testclient import TestClient

from app.backend.app.main import create_app
from app.backend.app.schemas.api import PairedResultsRequest
from app.backend.app.services.results_service import analyze_paired_results
from app.backend.app.stats.paired import (
    MCNEMAR_EXACT_MAX_DISCORDANT,
    mcnemar_test,
    paired_t_test,
    wilcoxon_signed_rank_test,
)

# Fixtures reused across the module (see the scratchpad verification for the frozen scipy numbers).
BEFORE = [10, 12, 9, 15, 11, 14, 8, 13, 10, 12]
AFTER = [12, 15, 10, 16, 13, 14, 11, 15, 12, 13]  # one zero difference (index 5)
# A zero difference (index 1) and six tied |d| = 2, for the Wilcoxon tie/zero path.
CTRL_TIES = [20, 22, 19, 25, 21, 24, 18, 23, 20, 22]
TREAT_TIES = [22, 22, 21, 24, 23, 26, 20, 23, 22, 25]


# --- paired t --------------------------------------------------------------------------------


def test_paired_t_matches_scipy_ttest_rel() -> None:
    result = paired_t_test(BEFORE, AFTER)
    assert result is not None
    # scipy.stats.ttest_rel(AFTER, BEFORE): t = 5.666666..., p = 0.0003070219963.
    assert result["test_statistic"] == pytest.approx(5.666666666667, abs=1e-9)
    assert result["p_value"] == pytest.approx(0.0003070219963, abs=1e-9)
    assert result["degrees_of_freedom"] == 9
    assert result["mean_difference"] == pytest.approx(1.7, abs=1e-12)
    # t-interval on the mean difference and Cohen's d_z (mean/sd of differences).
    assert result["ci_lower"] == pytest.approx(1.0213528512, abs=1e-7)
    assert result["ci_upper"] == pytest.approx(2.3786471488, abs=1e-7)
    assert result["effect_size"] == pytest.approx(1.7919573408, abs=1e-7)


def test_paired_t_with_ties_data_matches_scipy() -> None:
    result = paired_t_test(CTRL_TIES, TREAT_TIES)
    assert result is not None
    assert result["test_statistic"] == pytest.approx(3.5, abs=1e-9)
    assert result["p_value"] == pytest.approx(0.0067235157631, abs=1e-9)
    assert result["ci_lower"] == pytest.approx(0.4951371349, abs=1e-7)
    assert result["ci_upper"] == pytest.approx(2.3048628651, abs=1e-7)


def test_paired_t_degenerate_returns_none() -> None:
    # Constant difference (every pair moves by +1): zero variance, undefined t.
    assert paired_t_test([1, 2, 3], [2, 3, 4]) is None
    # Fewer than two pairs.
    assert paired_t_test([1], [2]) is None


def test_paired_t_rejects_non_finite() -> None:
    with pytest.raises(ValueError):
        paired_t_test([1.0, float("inf")], [2.0, 3.0])


# --- Wilcoxon signed-rank --------------------------------------------------------------------


def test_wilcoxon_zero_and_ties_matches_scipy() -> None:
    result = wilcoxon_signed_rank_test(CTRL_TIES, TREAT_TIES)
    assert result is not None
    # scipy.stats.wilcoxon(mode="approx", correction=True, zero_method="wilcox"): p = 0.0156734670.
    assert result["p_value"] == pytest.approx(0.0156734670, abs=1e-9)
    assert result["test_statistic"] == 1.0  # min(W+, W-) = min(35, 1)
    assert result["n_zero_differences"] == 2
    assert result["n_nonzero"] == 8
    assert result["effect_size"] == pytest.approx(0.9444444444, abs=1e-9)  # rank-biserial
    # Hodges–Lehmann pseudomedian of the paired differences and its distribution-free CI.
    assert result["pseudomedian"] == pytest.approx(2.0, abs=1e-12)
    assert result["ci_lower"] == pytest.approx(0.5, abs=1e-12)
    assert result["ci_upper"] == pytest.approx(2.0, abs=1e-12)


def test_wilcoxon_one_zero_matches_scipy() -> None:
    result = wilcoxon_signed_rank_test(BEFORE, AFTER)
    assert result is not None
    assert result["p_value"] == pytest.approx(0.0082583435, abs=1e-9)
    assert result["test_statistic"] == 0.0  # all non-zero differences positive
    assert result["n_zero_differences"] == 1
    assert result["effect_size"] == pytest.approx(1.0, abs=1e-12)
    assert result["pseudomedian"] == pytest.approx(1.5, abs=1e-12)
    assert result["ci_lower"] == pytest.approx(1.0, abs=1e-12)
    assert result["ci_upper"] == pytest.approx(2.5, abs=1e-12)


def test_wilcoxon_degenerate_returns_none() -> None:
    # All differences zero: no rank signal.
    assert wilcoxon_signed_rank_test([1, 1, 1], [1, 1, 1]) is None
    # Only one non-zero difference: fewer than two ranks to sign.
    assert wilcoxon_signed_rank_test([1, 1], [1, 2]) is None


# --- McNemar ---------------------------------------------------------------------------------


def test_mcnemar_exact_branch_matches_statsmodels() -> None:
    control = [0, 0, 0, 1, 1, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1]
    treatment = [1, 1, 1, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1, 1]
    result = mcnemar_test(control, treatment)
    assert result["discordant_positive"] == 7  # 0 -> 1
    assert result["discordant_negative"] == 0  # 1 -> 0
    assert result["method"] == "exact"
    # statsmodels mcnemar(exact=True): p = 0.015625 (two-sided binomial, min tail = 0).
    assert result["p_value"] == pytest.approx(0.015625, abs=1e-9)
    assert result["odds_ratio"] is None  # c = 0
    assert result["proportion_difference"] == pytest.approx(7 / 15, abs=1e-12)


def test_mcnemar_chi_square_branch_matches_statsmodels() -> None:
    # 39 discordant 0->1, 18 discordant 1->0, plus 143 concordant pairs (padding).
    control = [0] * 39 + [1] * 18 + [1] * 100 + [0] * 43
    treatment = [1] * 39 + [0] * 18 + [1] * 100 + [0] * 43
    result = mcnemar_test(control, treatment)
    assert result["discordant_positive"] == 39
    assert result["discordant_negative"] == 18
    assert result["method"] == "chi_square"
    # Edwards continuity-corrected chi-square (|39-18|-1)^2/57 = 7.017543...; p = 0.0080714874.
    assert result["test_statistic"] == pytest.approx(7.0175438596, abs=1e-9)
    assert result["p_value"] == pytest.approx(0.0080714874, abs=1e-9)
    assert result["odds_ratio"] == pytest.approx(39 / 18, abs=1e-9)


def test_mcnemar_equal_discordant_chi_square_matches_statsmodels() -> None:
    # b == c == 30 in the chi-square regime: statsmodels stat 0.016667, p 0.897279.
    control = [0] * 30 + [1] * 30
    treatment = [1] * 30 + [0] * 30
    result = mcnemar_test(control, treatment)
    assert result["method"] == "chi_square"
    assert result["test_statistic"] == pytest.approx(0.0166666667, abs=1e-9)
    assert result["p_value"] == pytest.approx(0.8972789613, abs=1e-9)
    assert result["proportion_difference"] == pytest.approx(0.0, abs=1e-12)


def test_mcnemar_no_discordant_pairs_is_p_one() -> None:
    result = mcnemar_test([1, 0, 1, 0], [1, 0, 1, 0])
    assert result["n_discordant"] == 0
    assert result["method"] == "exact"
    assert result["p_value"] == 1.0
    assert result["is_significant"] is False
    assert result["ci_lower"] == result["ci_upper"] == 0.0


def test_mcnemar_exact_threshold_boundary() -> None:
    # At exactly MCNEMAR_EXACT_MAX_DISCORDANT discordant pairs the chi-square branch takes over.
    n = MCNEMAR_EXACT_MAX_DISCORDANT
    control = [0] * n
    treatment = [1] * n  # all discordant 0 -> 1, n_discordant = n
    result = mcnemar_test(control, treatment)
    assert result["n_discordant"] == n
    assert result["method"] == "chi_square"
    below = mcnemar_test([0] * (n - 1), [1] * (n - 1))
    assert below["method"] == "exact"


# --- service layer ---------------------------------------------------------------------------


def test_service_paired_t_rounds_and_sets_verdict() -> None:
    response = analyze_paired_results(
        PairedResultsRequest(test_type="paired_t", control_values=BEFORE, treatment_values=AFTER)
    )
    assert response.test_type == "paired_t"
    assert response.n_pairs == 10
    assert response.effect == 1.7
    assert response.test_statistic == 5.6667  # rounded to 4 dp
    assert response.p_value == 0.000307  # rounded to 6 dp
    assert response.is_significant is True
    assert response.effect_size == 1.792
    assert "Cohen's dz" in response.interpretation


def test_service_wilcoxon_surfaces_zero_count() -> None:
    response = analyze_paired_results(
        PairedResultsRequest(test_type="wilcoxon", control_values=BEFORE, treatment_values=AFTER)
    )
    assert response.test_type == "wilcoxon"
    assert response.n_zero_differences == 1
    assert response.effect == 1.5
    assert response.effect_size == 1.0


def test_service_mcnemar_surfaces_discordant_counts() -> None:
    control = [0, 0, 0, 1, 1, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1]
    treatment = [1, 1, 1, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1, 1]
    response = analyze_paired_results(
        PairedResultsRequest(test_type="mcnemar", control_values=control, treatment_values=treatment)
    )
    assert response.test_type == "mcnemar"
    assert response.method == "exact"
    assert response.discordant_positive == 7
    assert response.discordant_negative == 0
    assert response.effect_size is None  # odds ratio undefined (c = 0)


def test_service_degenerate_paired_t_raises() -> None:
    with pytest.raises(ValueError):
        analyze_paired_results(
            PairedResultsRequest(test_type="paired_t", control_values=[1, 2], treatment_values=[2, 3])
        )


# --- HTTP endpoint ---------------------------------------------------------------------------


def test_endpoint_paired_t_round_trip() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/results/paired",
        json={"test_type": "paired_t", "control_values": BEFORE, "treatment_values": AFTER, "alpha": 0.05},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["test_type"] == "paired_t"
    assert body["p_value"] == 0.000307
    assert body["is_significant"] is True
    assert body["ci_level"] == 0.95


def test_endpoint_wilcoxon_round_trip() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/results/paired",
        json={"test_type": "wilcoxon", "control_values": CTRL_TIES, "treatment_values": TREAT_TIES},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["test_type"] == "wilcoxon"
    assert body["n_zero_differences"] == 2
    assert body["p_value"] == pytest.approx(0.015673, abs=1e-6)


def test_endpoint_mcnemar_round_trip() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/results/paired",
        json={
            "test_type": "mcnemar",
            "control_values": [0] * 39 + [1] * 18 + [1] * 100,
            "treatment_values": [1] * 39 + [0] * 18 + [1] * 100,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["method"] == "chi_square"
    assert body["p_value"] == pytest.approx(0.008071, abs=1e-6)
    assert body["discordant_positive"] == 39


def test_endpoint_localizes_via_accept_language() -> None:
    client = TestClient(create_app())
    body = {"test_type": "paired_t", "control_values": BEFORE, "treatment_values": AFTER}
    english = client.post("/api/v1/results/paired", json=body)
    russian = client.post("/api/v1/results/paired", json=body, headers={"Accept-Language": "ru"})
    assert english.status_code == 200 and russian.status_code == 200
    en, ru = english.json(), russian.json()
    assert ru["verdict"] != en["verdict"]
    # Numbers are language-independent.
    assert ru["p_value"] == en["p_value"]
    assert ru["effect"] == en["effect"]


def test_endpoint_length_mismatch_returns_422() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/results/paired",
        json={"test_type": "paired_t", "control_values": [1, 2, 3], "treatment_values": [1, 2]},
    )
    assert response.status_code == 422


def test_endpoint_mcnemar_non_binary_returns_422() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/results/paired",
        json={"test_type": "mcnemar", "control_values": [0, 1, 2], "treatment_values": [0, 1, 0]},
    )
    assert response.status_code == 422


def test_endpoint_degenerate_paired_t_returns_400() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/results/paired",
        json={"test_type": "paired_t", "control_values": [1, 2, 3], "treatment_values": [2, 3, 4]},
    )
    assert response.status_code == 400
