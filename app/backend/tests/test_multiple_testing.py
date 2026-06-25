"""Tests for the multiple-testing corrections (Benjamini-Hochberg FDR and Holm FWER).

The centerpiece is an empirical Monte-Carlo demonstration that the Benjamini-Hochberg procedure
keeps the realised false discovery rate at or below the nominal ``q`` under a mixture of true and
false null hypotheses, while testing each metric uncorrected at the same level inflates the FDR well
past ``q``. That contrast is the whole reason FDR control exists, so it is verified directly rather
than trusted from the closed form. The deterministic checks pin the implementation to the worked
example from Benjamini & Hochberg (1995).
"""

import random
import sys
from pathlib import Path
from statistics import NormalDist

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.stats.multiple_testing import benjamini_hochberg, holm_bonferroni

# --------------------------------------------------------------------------------------
# Literature reference: the Needleman et al. p-values used as the worked example in
# Benjamini & Hochberg (1995), Table 1. At q = 0.05 the BH procedure rejects the four
# smallest p-values (vs 11 uncorrected and 1 under Bonferroni) — their headline result.
# --------------------------------------------------------------------------------------
_BH1995_PVALUES = [
    0.0001, 0.0004, 0.0019, 0.0095, 0.0201, 0.0278, 0.0298, 0.0344,
    0.0459, 0.3240, 0.4262, 0.5719, 0.6528, 0.7590, 1.0000,
]


def test_bh_matches_benjamini_hochberg_1995_worked_example() -> None:
    result = benjamini_hochberg(_BH1995_PVALUES, q=0.05)
    # Four rejections at q = 0.05, the paper's headline.
    assert result["num_rejected"] == 4
    assert result["threshold_rank"] == 4
    # The largest rejected raw p-value is p(4) = 0.0095.
    assert result["critical_value"] == pytest.approx(0.0095)
    # Exactly the four smallest p-values are rejected.
    assert [result["rejected"][i] for i in range(15)] == [True] * 4 + [False] * 11


def test_bh_adjusted_pvalues_match_hand_computation() -> None:
    # Adjusted = cumulative-min from the tail of (m/k)*p(k). Spot-checked against R's
    # p.adjust(method = "BH") on the same vector.
    result = benjamini_hochberg(_BH1995_PVALUES, q=0.05)
    adjusted = result["adjusted_pvalues"]
    assert adjusted[0] == pytest.approx(0.0015, abs=1e-6)  # 15*0.0001/1
    assert adjusted[1] == pytest.approx(0.0030, abs=1e-6)  # 15*0.0004/2
    assert adjusted[2] == pytest.approx(0.0095, abs=1e-6)  # 15*0.0019/3
    assert adjusted[3] == pytest.approx(0.035625, abs=1e-6)  # 15*0.0095/4
    # Ranks 6 and 7 are pulled down to the rank-7 value by the monotonisation.
    assert adjusted[5] == pytest.approx(0.0638571, abs=1e-6)
    assert adjusted[6] == pytest.approx(0.0638571, abs=1e-6)
    assert adjusted[14] == pytest.approx(1.0, abs=1e-9)


def test_holm_matches_hand_computation_and_is_more_conservative_than_bh() -> None:
    holm = holm_bonferroni(_BH1995_PVALUES, alpha=0.05)
    # Holm steps down: p(4) = 0.0095 > 0.05/12 = 0.004167 stops the run -> 3 rejections.
    assert holm["num_rejected"] == 3
    adjusted = holm["adjusted_pvalues"]
    assert adjusted[0] == pytest.approx(0.0015, abs=1e-6)  # 15*0.0001
    assert adjusted[1] == pytest.approx(0.0056, abs=1e-6)  # 14*0.0004
    assert adjusted[2] == pytest.approx(0.0247, abs=1e-6)  # 13*0.0019
    assert adjusted[3] == pytest.approx(0.114, abs=1e-6)   # 12*0.0095
    # BH is uniformly at least as powerful as Holm on the same data.
    bh = benjamini_hochberg(_BH1995_PVALUES, q=0.05)
    assert bh["num_rejected"] >= holm["num_rejected"]


@pytest.mark.parametrize("procedure", [benjamini_hochberg, holm_bonferroni])
def test_single_metric_reduces_to_raw_test(procedure) -> None:  # type: ignore[no-untyped-def]
    # With m = 1 there is nothing to correct: adjusted == raw, rejected iff p <= level.
    below = procedure([0.03], 0.05)
    assert below["adjusted_pvalues"] == [pytest.approx(0.03)]
    assert below["rejected"] == [True]
    assert below["num_rejected"] == 1
    above = procedure([0.20], 0.05)
    assert above["adjusted_pvalues"] == [pytest.approx(0.20)]
    assert above["rejected"] == [False]
    assert above["num_rejected"] == 0


@pytest.mark.parametrize("procedure", [benjamini_hochberg, holm_bonferroni])
def test_rejection_is_dual_to_adjusted_pvalue_threshold(procedure) -> None:  # type: ignore[no-untyped-def]
    # A metric is rejected exactly when its adjusted p-value is at or below the level.
    level = 0.05
    pvalues = [0.001, 0.008, 0.02, 0.04, 0.06, 0.2, 0.5, 0.9, 0.03, 0.011]
    result = procedure(pvalues, level)
    for rejected, adjusted in zip(result["rejected"], result["adjusted_pvalues"]):
        assert rejected == (adjusted <= level)
    assert result["num_rejected"] == sum(result["rejected"])


@pytest.mark.parametrize("procedure", [benjamini_hochberg, holm_bonferroni])
def test_rejection_set_respects_pvalue_ordering(procedure) -> None:  # type: ignore[no-untyped-def]
    # Monotonicity: a smaller p-value can never be left out while a larger one is rejected, so
    # every rejected metric has a p-value at or below every non-rejected one.
    pvalues = [0.5, 0.001, 0.04, 0.2, 0.009, 0.03, 0.7, 0.012]
    result = procedure(pvalues, 0.05)
    rejected_p = [p for p, r in zip(pvalues, result["rejected"]) if r]
    kept_p = [p for p, r in zip(pvalues, result["rejected"]) if not r]
    if rejected_p and kept_p:
        assert max(rejected_p) <= min(kept_p)


def test_bh_adjusted_pvalues_are_monotone_in_rank() -> None:
    pvalues = [0.5, 0.001, 0.04, 0.2, 0.009, 0.03, 0.7, 0.012, 0.06, 0.5]
    result = benjamini_hochberg(pvalues, 0.05)
    by_rank = sorted(zip(pvalues, result["adjusted_pvalues"]), key=lambda pair: pair[0])
    adjusted_in_rank_order = [adj for _, adj in by_rank]
    assert all(
        adjusted_in_rank_order[i] <= adjusted_in_rank_order[i + 1] + 1e-12
        for i in range(len(adjusted_in_rank_order) - 1)
    )


def test_results_keep_input_order_under_shuffle() -> None:
    pvalues = [0.5, 0.001, 0.04, 0.2, 0.009, 0.03, 0.7, 0.012]
    result = benjamini_hochberg(pvalues, 0.05)
    # The smallest p-value (index 1) must be the most-rejected / smallest-adjusted entry.
    assert result["rejected"][1] is True
    assert result["adjusted_pvalues"][1] == min(result["adjusted_pvalues"])
    # A clearly non-significant p-value (index 6, p = 0.7) is never rejected.
    assert result["rejected"][6] is False


@pytest.mark.parametrize("procedure", [benjamini_hochberg, holm_bonferroni])
@pytest.mark.parametrize(
    "pvalues, level",
    [
        ([], 0.05),            # empty
        ([0.1, 1.5], 0.05),    # p-value > 1
        ([0.1, -0.01], 0.05),  # p-value < 0
        ([0.1, 0.2], 0.0),     # level at boundary
        ([0.1, 0.2], 1.0),     # level at boundary
    ],
)
def test_invalid_inputs_raise(procedure, pvalues, level) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        procedure(pvalues, level)


# --------------------------------------------------------------------------------------
# Monte-Carlo: BH controls the realised FDR; testing uncorrected at the same level does not.
# --------------------------------------------------------------------------------------
def _simulate_fdr(
    *,
    num_metrics: int,
    num_true_nulls: int,
    effect: float,
    q: float,
    n_sim: int,
    seed: int,
) -> tuple[float, float]:
    """Return ``(bh_fdr, uncorrected_fdr)`` over ``n_sim`` families of one-sided z-test p-values.

    True nulls draw ``Z ~ N(0, 1)`` (so their p-values are Uniform(0, 1)); false nulls draw
    ``Z ~ N(effect, 1)``. The false discovery proportion of a run is ``V / max(R, 1)`` where ``R``
    is the number rejected and ``V`` the number of those that were true nulls.
    """
    rng = random.Random(seed)
    normal = NormalDist()
    bh_fdp_total = 0.0
    uncorrected_fdp_total = 0.0

    for _ in range(n_sim):
        pvalues: list[float] = []
        is_true_null: list[bool] = []
        for metric in range(num_metrics):
            true_null = metric < num_true_nulls
            z = rng.gauss(0.0, 1.0) if true_null else rng.gauss(effect, 1.0)
            pvalues.append(1.0 - normal.cdf(z))  # one-sided (upper tail)
            is_true_null.append(true_null)

        bh_rejected = benjamini_hochberg(pvalues, q=q)["rejected"]
        bh_r = sum(bh_rejected)
        bh_v = sum(1 for rej, null in zip(bh_rejected, is_true_null) if rej and null)
        bh_fdp_total += bh_v / max(bh_r, 1)

        unc_rejected = [p <= q for p in pvalues]
        unc_r = sum(unc_rejected)
        unc_v = sum(1 for rej, null in zip(unc_rejected, is_true_null) if rej and null)
        uncorrected_fdp_total += unc_v / max(unc_r, 1)

    return bh_fdp_total / n_sim, uncorrected_fdp_total / n_sim


def test_bh_controls_fdr_while_uncorrected_testing_inflates_it() -> None:
    # 15 of 20 metrics are true nulls, the other 5 carry a strong effect.
    bh_fdr, uncorrected_fdr = _simulate_fdr(
        num_metrics=20,
        num_true_nulls=15,
        effect=3.0,
        q=0.10,
        n_sim=600,
        seed=20260625,
    )
    # BH bounds the FDR at (m0/m)*q = 0.75*0.10 = 0.075 <= q; the cushion absorbs MC noise.
    assert bh_fdr <= 0.11, f"BH did not control FDR: {bh_fdr}"
    # Testing each metric uncorrected at the same level lets the FDR run well past q.
    assert uncorrected_fdr > 0.15, f"expected uncorrected FDR to inflate, got {uncorrected_fdr}"
    assert bh_fdr < uncorrected_fdr
