"""Metric capability registry — single source of truth (audit F-11).

Planning metric families live in ``constants.MetricType`` / ``METRIC_TYPES``.
This module adds *capabilities* (what each family can do) and the post-hoc
two-sample analyzer registry used by ``results.dispatch``, so adding a family
means editing one place instead of parallel unions/if-ladders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from app.backend.app.constants import METRIC_TYPES, MetricType

# Payload shape on ResultsRequest for independent two-sample analyzers.
ResultsPayloadKind = Literal["binary", "continuous", "ranked", "count"]

# Analyzer ids accepted by ResultsRequest.metric_type (must stay in lockstep with
# schemas.api._results.ResultsRequest and the frontend ObservedResults types).
ResultsAnalyzerType = Literal[
    "binary",
    "continuous",
    "equivalence",
    "mann_whitney",
    "bootstrap",
    "quantile",
    "trimmed_t",
    "fisher_exact",
    "boschloo_exact",
    "barnard_exact",
    "count",
]


@dataclass(frozen=True, slots=True)
class PlanningCapability:
    """What the planner / live executor / post-hoc surface support for a design metric."""

    metric_type: MetricType
    sample_size_planning: bool
    # Continuous and ratio sizing need a per-user std_dev (delta-method for ratio).
    requires_std_dev: bool
    # Live experiment primary comparison path.
    live_primary_stats: bool
    # CUPED applies to continuous-valued outcomes (not rates/counts/ratios as primary).
    cuped_eligible: bool
    # Post-hoc entry: independent two-sample ResultsRequest family, ratio endpoint, or none.
    post_hoc_route: Literal["results", "results_ratio", "none"]


PLANNING_CAPABILITIES: Final[dict[MetricType, PlanningCapability]] = {
    "binary": PlanningCapability(
        metric_type="binary",
        sample_size_planning=True,
        requires_std_dev=False,
        live_primary_stats=True,
        cuped_eligible=False,
        post_hoc_route="results",
    ),
    "continuous": PlanningCapability(
        metric_type="continuous",
        sample_size_planning=True,
        requires_std_dev=True,
        live_primary_stats=True,
        cuped_eligible=True,
        post_hoc_route="results",
    ),
    "ratio": PlanningCapability(
        metric_type="ratio",
        sample_size_planning=True,
        requires_std_dev=True,
        live_primary_stats=True,
        cuped_eligible=False,
        post_hoc_route="results_ratio",
    ),
    "count": PlanningCapability(
        metric_type="count",
        sample_size_planning=True,
        requires_std_dev=False,
        live_primary_stats=True,
        cuped_eligible=False,
        post_hoc_route="results",
    ),
}


@dataclass(frozen=True, slots=True)
class ResultsAnalyzerCapability:
    """Post-hoc independent two-sample analyzer → payload field on ResultsRequest."""

    metric_type: ResultsAnalyzerType
    payload_kind: ResultsPayloadKind
    # Planning family this analyzer belongs to (for UI grouping / drift checks).
    planning_family: MetricType


RESULTS_ANALYZERS: Final[dict[str, ResultsAnalyzerCapability]] = {
    "binary": ResultsAnalyzerCapability("binary", "binary", "binary"),
    "fisher_exact": ResultsAnalyzerCapability("fisher_exact", "binary", "binary"),
    "boschloo_exact": ResultsAnalyzerCapability("boschloo_exact", "binary", "binary"),
    "barnard_exact": ResultsAnalyzerCapability("barnard_exact", "binary", "binary"),
    "continuous": ResultsAnalyzerCapability("continuous", "continuous", "continuous"),
    "equivalence": ResultsAnalyzerCapability("equivalence", "continuous", "continuous"),
    "mann_whitney": ResultsAnalyzerCapability("mann_whitney", "ranked", "continuous"),
    "bootstrap": ResultsAnalyzerCapability("bootstrap", "ranked", "continuous"),
    "quantile": ResultsAnalyzerCapability("quantile", "ranked", "continuous"),
    "trimmed_t": ResultsAnalyzerCapability("trimmed_t", "ranked", "continuous"),
    "count": ResultsAnalyzerCapability("count", "count", "count"),
}

RESULTS_ANALYZER_TYPES: Final[tuple[str, ...]] = tuple(RESULTS_ANALYZERS.keys())


def planning_capability(metric_type: str) -> PlanningCapability:
    """Look up planning capabilities; raises KeyError for unknown families."""
    return PLANNING_CAPABILITIES[metric_type]  # type: ignore[index]


def requires_std_dev_for_planning(metric_type: str) -> bool:
    if metric_type not in PLANNING_CAPABILITIES:
        return False
    return PLANNING_CAPABILITIES[metric_type].requires_std_dev  # type: ignore[index]


def results_payload_kind(metric_type: str) -> ResultsPayloadKind:
    return RESULTS_ANALYZERS[metric_type].payload_kind


def assert_registry_covers_planning_types() -> None:
    """Invariant: every MetricType has a planning capability entry."""
    missing = set(METRIC_TYPES) - set(PLANNING_CAPABILITIES)
    if missing:
        raise AssertionError(f"PLANNING_CAPABILITIES missing metric types: {sorted(missing)}")
    extra = set(PLANNING_CAPABILITIES) - set(METRIC_TYPES)
    if extra:
        raise AssertionError(f"PLANNING_CAPABILITIES has unknown metric types: {sorted(extra)}")


assert_registry_covers_planning_types()
