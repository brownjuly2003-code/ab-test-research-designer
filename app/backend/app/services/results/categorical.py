"""r×c independence analyzers (chi-square / G-test)."""
from __future__ import annotations

from typing import Any

from app.backend.app.i18n import translate
from app.backend.app.schemas.api import (
    CategoricalResultsRequest,
    CategoricalResultsResponse,
)
from app.backend.app.stats.chi_square_independence import (
    chi_square_independence_test,
    g_test_independence,
)


def analyze_categorical_results(request: CategoricalResultsRequest) -> CategoricalResultsResponse:
    """Test of independence on an r×c contingency table — Pearson chi-square or the G-test.

    Separate from ``analyze_results`` because the outcome is omnibus — a test statistic with degrees of
    freedom and Cramér's V, not the scalar effect + confidence interval that ``ResultsResponse`` carries.
    ``test_type`` selects Pearson's chi-square (default) or the G-test (likelihood-ratio chi-square) on
    the same table; both share this response shape. A degenerate table raises ``ValueError`` from the
    stats layer, which the global handler maps to HTTP 400.
    """
    if request.test_type == "g_test":
        result = g_test_independence(request.table, request.alpha)
    else:
        result = chi_square_independence_test(request.table, request.alpha)
    is_significant = result["is_significant"]
    return CategoricalResultsResponse(
        test_type=request.test_type,
        chi_square=round(result["chi_square"], 4),
        degrees_of_freedom=result["degrees_of_freedom"],
        p_value=round(result["p_value"], 6),
        is_significant=is_significant,
        cramers_v=round(result["cramers_v"], 4),
        n_total=result["n_total"],
        num_rows=result["num_rows"],
        num_cols=result["num_cols"],
        min_expected_count=round(result["min_expected_count"], 4),
        low_expected_warning=result["low_expected_warning"],
        verdict=translate(
            "results.categorical.verdict_associated"
            if is_significant
            else "results.categorical.verdict_independent"
        ),
        interpretation=_interpretation_categorical(result, request.test_type),
    )


def _interpretation_categorical(result: dict[str, Any], test_type: str) -> str:
    significance_text = translate(
        "results.significance.significant"
        if result["is_significant"]
        else "results.significance.not_significant"
    )
    return translate(
        "results.interpretation.g_test" if test_type == "g_test" else "results.interpretation.categorical",
        {
            "chiSquare": f"{result['chi_square']:.4f}",
            "df": str(result["degrees_of_freedom"]),
            "rows": str(result["num_rows"]),
            "cols": str(result["num_cols"]),
            "n": str(result["n_total"]),
            "pValue": f"{result['p_value']:.6f}",
            "cramersV": f"{result['cramers_v']:.4f}",
            "significance": significance_text,
        },
    )

