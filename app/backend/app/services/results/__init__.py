"""Post-hoc results analyzers by metric/family.

Public entry points match the historical `results_service` module. Domain
blocks live in sibling modules so each analyzer family stays readable. The
import path `services.results_service` remains a stable facade.
"""

from .categorical import analyze_categorical_results
from .common import standard_normal_cdf
from .dispatch import analyze_results
from .omnibus import analyze_omnibus_results
from .paired import analyze_paired_results
from .ratio import analyze_ratio_results, build_ratio_results_response
from .survival import analyze_survival_results

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
