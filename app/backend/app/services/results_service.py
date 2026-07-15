"""Facade for post-hoc results analyzers (audit F-11).

Stable import path used by routes and tests. Implementation lives in
`app.backend.app.services.results`.
"""

from app.backend.app.services.results import (
    analyze_categorical_results,
    analyze_omnibus_results,
    analyze_paired_results,
    analyze_ratio_results,
    analyze_results,
    analyze_survival_results,
    build_ratio_results_response,
    standard_normal_cdf,
)

__all__ = [
    "analyze_results",
    "analyze_categorical_results",
    "analyze_paired_results",
    "analyze_omnibus_results",
    "analyze_survival_results",
    "analyze_ratio_results",
    "build_ratio_results_response",
    "standard_normal_cdf",
]
