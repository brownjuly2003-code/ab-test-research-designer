"""Metric-type registry for the independent two-sample ResultsRequest family."""
from __future__ import annotations

from collections.abc import Callable
from typing import Final

from app.backend.app.metric_capabilities import RESULTS_ANALYZER_TYPES
from app.backend.app.schemas.api import ResultsRequest, ResultsResponse

from .binary import _analyze_binary
from .continuous import (
    _analyze_bootstrap,
    _analyze_continuous,
    _analyze_equivalence,
    _analyze_mann_whitney,
    _analyze_quantile,
    _analyze_trimmed_t,
)
from .count import _analyze_count
from .exact import (
    _analyze_barnard_exact,
    _analyze_boschloo_exact,
    _analyze_fisher_exact,
)

_Analyzer = Callable[[ResultsRequest], ResultsResponse]

# Handlers are keyed by the capability registry ids so a new analyzer is added
# once in metric_capabilities.RESULTS_ANALYZERS and once here — not as a third
# if-ladder in this file.
_RESULTS_HANDLERS: Final[dict[str, _Analyzer]] = {
    "binary": lambda request: _analyze_binary(request.binary),
    "fisher_exact": lambda request: _analyze_fisher_exact(request.binary),
    "boschloo_exact": lambda request: _analyze_boschloo_exact(request.binary),
    "barnard_exact": lambda request: _analyze_barnard_exact(request.binary),
    "mann_whitney": lambda request: _analyze_mann_whitney(request.ranked),
    "bootstrap": lambda request: _analyze_bootstrap(request.ranked),
    "quantile": lambda request: _analyze_quantile(request.ranked),
    "trimmed_t": lambda request: _analyze_trimmed_t(request.ranked),
    "count": lambda request: _analyze_count(request.count),
    "equivalence": lambda request: _analyze_equivalence(request.continuous),
    "continuous": lambda request: _analyze_continuous(request.continuous),
}


def _assert_handlers_cover_registry() -> None:
    missing = set(RESULTS_ANALYZER_TYPES) - set(_RESULTS_HANDLERS)
    if missing:
        raise AssertionError(f"results dispatch missing handlers: {sorted(missing)}")
    extra = set(_RESULTS_HANDLERS) - set(RESULTS_ANALYZER_TYPES)
    if extra:
        raise AssertionError(f"results dispatch has unknown handlers: {sorted(extra)}")


_assert_handlers_cover_registry()


def analyze_results(request: ResultsRequest) -> ResultsResponse:
    handler = _RESULTS_HANDLERS.get(request.metric_type)
    if handler is None:
        # Pydantic Literal should make this unreachable; fall back keeps a clear error.
        raise ValueError(f"Unsupported results metric_type: {request.metric_type}")
    return handler(request)
