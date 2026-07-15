"""Metric-type registry for the independent two-sample ResultsRequest family."""
from __future__ import annotations

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


def analyze_results(request: ResultsRequest) -> ResultsResponse:
    if request.metric_type == "binary":
        return _analyze_binary(request.binary)
    if request.metric_type == "fisher_exact":
        return _analyze_fisher_exact(request.binary)
    if request.metric_type == "boschloo_exact":
        return _analyze_boschloo_exact(request.binary)
    if request.metric_type == "barnard_exact":
        return _analyze_barnard_exact(request.binary)
    if request.metric_type == "mann_whitney":
        return _analyze_mann_whitney(request.ranked)
    if request.metric_type == "bootstrap":
        return _analyze_bootstrap(request.ranked)
    if request.metric_type == "quantile":
        return _analyze_quantile(request.ranked)
    if request.metric_type == "trimmed_t":
        return _analyze_trimmed_t(request.ranked)
    if request.metric_type == "count":
        return _analyze_count(request.count)
    if request.metric_type == "equivalence":
        return _analyze_equivalence(request.continuous)
    return _analyze_continuous(request.continuous)

