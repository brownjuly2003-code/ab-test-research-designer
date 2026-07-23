"""Cost-aware admission control for expensive analysis endpoints (audit F-06).

Request-count rate limits remain the first line of defence in HTTP middleware.
This module is the second layer: it estimates relative CPU cost from validated
request shape *before* resampling / exact enumeration starts, then admits or
load-sheds against bounded concurrency and in-flight cost budgets.

Cost units are intentionally coarse and method-relative, not wall-clock ms:
they only need to separate cheap summary tests from bootstrap/quantile/exact
work so a burst of heavy `/results` calls cannot monopolise workers while
cheap calculators stay responsive.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from math import ceil
from threading import Condition, Lock
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal

from app.backend.app.stats.bootstrap_permutation import (
    DEFAULT_RESAMPLES as BOOTSTRAP_RESAMPLES,
)
from app.backend.app.stats.quantile_te import DEFAULT_RESAMPLES as QUANTILE_RESAMPLES

if TYPE_CHECKING:
    from app.backend.app.schemas.api import (
        BanditSimulationRequest,
        CategoricalResultsRequest,
        OmnibusResultsRequest,
        PairedResultsRequest,
        RatioResultsRequest,
        ResultsRequest,
        SurvivalResultsRequest,
    )

Lane = Literal["cheap", "heavy"]


@dataclass(frozen=True)
class AdmissionDecision:
    allowed: bool
    cost_units: int = 0
    lane: Lane = "cheap"
    retry_after_seconds: int = 0
    reason: str | None = None


@dataclass(frozen=True)
class CostEstimate:
    cost_units: int
    lane: Lane
    analyzer: str
    n_total: int = 0
    n_resamples: int = 0


# Relative weights: cheap summary tests stay near 1; resampling and unconditional
# exact methods scale with sample/table size. Thresholds are calibrated so that
# a small binary test is always cheap and a 1k+1k bootstrap is always heavy.
_HEAVY_COST_THRESHOLD = 8


def _lane_for_cost(cost_units: int) -> Lane:
    return "heavy" if cost_units >= _HEAVY_COST_THRESHOLD else "cheap"


def estimate_results_cost(request: ResultsRequest) -> CostEstimate:
    """Estimate cost for POST /api/v1/results after schema validation."""
    metric = request.metric_type
    if metric in {"binary", "fisher_exact", "boschloo_exact", "barnard_exact"}:
        assert request.binary is not None
        n_c = request.binary.control_users
        n_t = request.binary.treatment_users
        n_total = n_c + n_t
        if metric == "binary":
            cost = 1
        elif metric == "fisher_exact":
            # Single-margin hypergeometric sweep: roughly O(min(n_c, n_t)).
            cost = max(2, ceil(min(n_c, n_t) / 25))
        else:
            # Unconditional exact (Barnard/Boschloo): O((n_c+1)(n_t+1) * grid).
            cost = max(12, ceil(((n_c + 1) * (n_t + 1)) / 50))
        return CostEstimate(cost_units=cost, lane=_lane_for_cost(cost), analyzer=metric, n_total=n_total)

    if metric in {"continuous", "equivalence"}:
        assert request.continuous is not None
        n_total = request.continuous.control_n + request.continuous.treatment_n
        cost = 1
        return CostEstimate(cost_units=cost, lane="cheap", analyzer=metric, n_total=n_total)

    if metric == "count":
        cost = 1
        return CostEstimate(cost_units=cost, lane="cheap", analyzer=metric, n_total=0)

    if metric in {"mann_whitney", "bootstrap", "quantile", "trimmed_t"}:
        assert request.ranked is not None
        n_c = len(request.ranked.control_values)
        n_t = len(request.ranked.treatment_values)
        n_total = n_c + n_t
        if metric == "mann_whitney":
            # Hodges–Lehmann materialises pairwise differences: O(n_c * n_t).
            cost = max(3, ceil((n_c * n_t) / 50_000))
            resamples = 0
        elif metric == "trimmed_t":
            cost = max(2, ceil(n_total / 200))
            resamples = 0
        elif metric == "bootstrap":
            resamples = BOOTSTRAP_RESAMPLES
            # Two passes of n_resamples over both arms.
            cost = max(10, ceil((n_total * resamples) / 100_000))
        else:  # quantile
            resamples = QUANTILE_RESAMPLES
            cost = max(12, ceil((n_total * resamples) / 80_000))
        return CostEstimate(
            cost_units=cost,
            lane=_lane_for_cost(cost),
            analyzer=metric,
            n_total=n_total,
            n_resamples=resamples,
        )

    cost = 2
    return CostEstimate(cost_units=cost, lane=_lane_for_cost(cost), analyzer=metric)


def estimate_categorical_cost(request: CategoricalResultsRequest) -> CostEstimate:
    rows = len(request.table)
    cols = len(request.table[0]) if request.table else 0
    cells = rows * cols
    cost = max(2, ceil(cells / 20))
    return CostEstimate(cost_units=cost, lane=_lane_for_cost(cost), analyzer="categorical", n_total=cells)


def estimate_paired_cost(request: PairedResultsRequest) -> CostEstimate:
    n = len(request.control_values)
    cost = max(1, ceil(max(n, 1) / 200))
    return CostEstimate(cost_units=cost, lane=_lane_for_cost(cost), analyzer=request.test_type, n_total=n)


def estimate_omnibus_cost(request: OmnibusResultsRequest) -> CostEstimate:
    n_total = sum(len(group) for group in request.groups)
    cost = max(2, ceil(n_total / 150))
    return CostEstimate(
        cost_units=cost,
        lane=_lane_for_cost(cost),
        analyzer=request.test_type,
        n_total=n_total,
    )


def estimate_survival_cost(request: SurvivalResultsRequest) -> CostEstimate:
    arms = [request.control_arm, request.treatment_arm, *request.additional_arms]
    n_total = sum(len(arm.durations) for arm in arms)
    cost = max(3, ceil(max(n_total, 1) / 100))
    return CostEstimate(
        cost_units=cost,
        lane=_lane_for_cost(cost),
        analyzer=request.test_type,
        n_total=n_total,
    )


def estimate_ratio_cost(request: RatioResultsRequest) -> CostEstimate:
    n_total = len(request.control_arm.numerators) + len(request.treatment_arm.numerators)
    cost = max(2, ceil(max(n_total, 1) / 200))
    return CostEstimate(cost_units=cost, lane=_lane_for_cost(cost), analyzer="ratio", n_total=n_total)


def estimate_bandit_cost(request: BanditSimulationRequest) -> CostEstimate:
    sims = int(request.num_simulations)
    horizon = int(request.horizon)
    cost = max(15, ceil((sims * horizon) / 50_000))
    return CostEstimate(
        cost_units=cost,
        lane="heavy",
        analyzer="bandit",
        n_total=sims,
        n_resamples=horizon,
    )


class ComputeAdmissionController:
    """Process-local bounded concurrency + in-flight cost budget for heavy work."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        max_heavy_concurrent: int = 2,
        max_cheap_concurrent: int = 32,
        max_cost_units_in_flight: int = 80,
        acquire_timeout_seconds: float = 0.05,
        retry_after_seconds: int = 2,
    ) -> None:
        if max_heavy_concurrent < 1:
            raise ValueError("max_heavy_concurrent must be at least 1")
        if max_cheap_concurrent < 1:
            raise ValueError("max_cheap_concurrent must be at least 1")
        if max_cost_units_in_flight < 1:
            raise ValueError("max_cost_units_in_flight must be at least 1")
        self.enabled = enabled
        self.max_heavy_concurrent = max_heavy_concurrent
        self.max_cheap_concurrent = max_cheap_concurrent
        self.max_cost_units_in_flight = max_cost_units_in_flight
        self.acquire_timeout_seconds = acquire_timeout_seconds
        self.retry_after_seconds = max(1, retry_after_seconds)
        self._lock = Lock()
        self._condition = Condition(self._lock)
        self._heavy_in_flight = 0
        self._cheap_in_flight = 0
        self._cost_in_flight = 0
        self._admitted = 0
        self._rejected = 0
        self._rejected_by_analyzer: dict[str, int] = {}
        self._peak_heavy = 0
        self._peak_cost = 0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.enabled,
                "heavy_in_flight": self._heavy_in_flight,
                "cheap_in_flight": self._cheap_in_flight,
                "cost_units_in_flight": self._cost_in_flight,
                "max_heavy_concurrent": self.max_heavy_concurrent,
                "max_cheap_concurrent": self.max_cheap_concurrent,
                "max_cost_units_in_flight": self.max_cost_units_in_flight,
                "admitted": self._admitted,
                "rejected": self._rejected,
                "rejected_by_analyzer": dict(self._rejected_by_analyzer),
                "peak_heavy_in_flight": self._peak_heavy,
                "peak_cost_units_in_flight": self._peak_cost,
            }

    def _try_admit_locked(self, estimate: CostEstimate) -> AdmissionDecision:
        if not self.enabled:
            return AdmissionDecision(allowed=True, cost_units=estimate.cost_units, lane=estimate.lane)

        if estimate.lane == "heavy":
            if self._heavy_in_flight >= self.max_heavy_concurrent:
                return AdmissionDecision(
                    allowed=False,
                    cost_units=estimate.cost_units,
                    lane=estimate.lane,
                    retry_after_seconds=self.retry_after_seconds,
                    reason="heavy_concurrency",
                )
            # Cost budget limits concurrent heavy work. A solo request always proceeds
            # even when its estimate exceeds the nominal budget — schema/service caps
            # already bound worst-case single-call work (e.g. unconditional exact n≤200).
            if (
                self._heavy_in_flight > 0
                and self._cost_in_flight + estimate.cost_units > self.max_cost_units_in_flight
            ):
                return AdmissionDecision(
                    allowed=False,
                    cost_units=estimate.cost_units,
                    lane=estimate.lane,
                    retry_after_seconds=self.retry_after_seconds,
                    reason="cost_budget",
                )
            self._heavy_in_flight += 1
            self._cost_in_flight += estimate.cost_units
            self._peak_heavy = max(self._peak_heavy, self._heavy_in_flight)
            self._peak_cost = max(self._peak_cost, self._cost_in_flight)
        else:
            if self._cheap_in_flight >= self.max_cheap_concurrent:
                return AdmissionDecision(
                    allowed=False,
                    cost_units=estimate.cost_units,
                    lane=estimate.lane,
                    retry_after_seconds=self.retry_after_seconds,
                    reason="cheap_concurrency",
                )
            self._cheap_in_flight += 1
            # Cheap work still consumes a small cost unit so pathological cheap
            # floods remain bounded, but never blocks heavy budget exclusively.
            self._cost_in_flight += min(estimate.cost_units, 1)
            self._peak_cost = max(self._peak_cost, self._cost_in_flight)

        self._admitted += 1
        return AdmissionDecision(allowed=True, cost_units=estimate.cost_units, lane=estimate.lane)

    def _release_locked(self, estimate: CostEstimate) -> None:
        if estimate.lane == "heavy":
            self._heavy_in_flight = max(0, self._heavy_in_flight - 1)
            self._cost_in_flight = max(0, self._cost_in_flight - estimate.cost_units)
        else:
            self._cheap_in_flight = max(0, self._cheap_in_flight - 1)
            self._cost_in_flight = max(0, self._cost_in_flight - min(estimate.cost_units, 1))
        self._condition.notify_all()

    def _record_rejection_locked(self, analyzer: str) -> None:
        self._rejected += 1
        self._rejected_by_analyzer[analyzer] = self._rejected_by_analyzer.get(analyzer, 0) + 1

    @contextmanager
    def admit(self, estimate: CostEstimate) -> Iterator[AdmissionDecision]:
        """Attempt to admit work; on success hold the slot until the block exits.

        Fast load-shedding: wait at most ``acquire_timeout_seconds`` for a free
        slot, then reject with Retry-After rather than queueing unbounded CPU work.
        """
        if not self.enabled:
            yield AdmissionDecision(allowed=True, cost_units=estimate.cost_units, lane=estimate.lane)
            return

        deadline = monotonic() + self.acquire_timeout_seconds
        decision: AdmissionDecision
        with self._condition:
            while True:
                decision = self._try_admit_locked(estimate)
                if decision.allowed:
                    break
                remaining = deadline - monotonic()
                if remaining <= 0:
                    self._record_rejection_locked(estimate.analyzer)
                    break
                self._condition.wait(timeout=remaining)
            if not decision.allowed:
                yield decision
                return

        try:
            yield decision
        finally:
            with self._condition:
                self._release_locked(estimate)
