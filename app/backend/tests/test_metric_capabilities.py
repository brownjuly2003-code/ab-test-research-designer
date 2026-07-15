"""Registry invariants for planning + post-hoc metric capabilities (audit F-11)."""

from typing import get_args

from app.backend.app.constants import METRIC_TYPES
from app.backend.app.metric_capabilities import (
    PLANNING_CAPABILITIES,
    RESULTS_ANALYZER_TYPES,
    RESULTS_ANALYZERS,
    requires_std_dev_for_planning,
    results_payload_kind,
)
from app.backend.app.schemas.api import ResultsRequest
from app.backend.app.services.results.dispatch import _RESULTS_HANDLERS


def test_planning_capabilities_cover_metric_types() -> None:
    assert set(PLANNING_CAPABILITIES) == set(METRIC_TYPES)


def test_requires_std_dev_matches_continuous_and_ratio() -> None:
    assert requires_std_dev_for_planning("binary") is False
    assert requires_std_dev_for_planning("count") is False
    assert requires_std_dev_for_planning("continuous") is True
    assert requires_std_dev_for_planning("ratio") is True
    assert requires_std_dev_for_planning("unknown") is False


def test_results_analyzers_match_schema_literal() -> None:
    schema_types = set(get_args(ResultsRequest.model_fields["metric_type"].annotation))
    assert set(RESULTS_ANALYZER_TYPES) == schema_types
    assert set(RESULTS_ANALYZERS) == schema_types


def test_results_handlers_cover_registry() -> None:
    assert set(_RESULTS_HANDLERS) == set(RESULTS_ANALYZER_TYPES)


def test_results_payload_kinds() -> None:
    assert results_payload_kind("binary") == "binary"
    assert results_payload_kind("fisher_exact") == "binary"
    assert results_payload_kind("continuous") == "continuous"
    assert results_payload_kind("equivalence") == "continuous"
    assert results_payload_kind("mann_whitney") == "ranked"
    assert results_payload_kind("count") == "count"


def test_ratio_is_separate_post_hoc_route() -> None:
    assert PLANNING_CAPABILITIES["ratio"].post_hoc_route == "results_ratio"
    assert "ratio" not in RESULTS_ANALYZERS
