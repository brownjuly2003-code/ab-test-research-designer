"""Unit tests for cost estimation and compute admission (audit F-06)."""

import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.compute_admission import (
    ComputeAdmissionController,
    CostEstimate,
    estimate_results_cost,
)
from app.backend.app.config import get_settings
from app.backend.app.main import create_app
from app.backend.app.schemas.api import (
    ObservedResultsBinary,
    ObservedResultsContinuous,
    ObservedResultsRanked,
    ResultsRequest,
)


def test_binary_results_are_cheap() -> None:
    request = ResultsRequest(
        metric_type="binary",
        binary=ObservedResultsBinary(
            control_conversions=50,
            control_users=1000,
            treatment_conversions=60,
            treatment_users=1000,
        ),
    )
    estimate = estimate_results_cost(request)
    assert estimate.lane == "cheap"
    assert estimate.cost_units == 1
    assert estimate.analyzer == "binary"


def test_bootstrap_large_sample_is_heavy() -> None:
    control = [float(i) for i in range(500)]
    treatment = [float(i) + 0.5 for i in range(500)]
    request = ResultsRequest(
        metric_type="bootstrap",
        ranked=ObservedResultsRanked(control_values=control, treatment_values=treatment),
    )
    estimate = estimate_results_cost(request)
    assert estimate.lane == "heavy"
    assert estimate.cost_units >= 10
    assert estimate.n_resamples == 2000
    assert estimate.n_total == 1000


def test_barnard_exact_large_table_is_heavy() -> None:
    request = ResultsRequest(
        metric_type="barnard_exact",
        binary=ObservedResultsBinary(
            control_conversions=40,
            control_users=100,
            treatment_conversions=55,
            treatment_users=100,
        ),
    )
    estimate = estimate_results_cost(request)
    assert estimate.lane == "heavy"
    assert estimate.cost_units >= 12


def test_continuous_summary_stays_cheap() -> None:
    request = ResultsRequest(
        metric_type="continuous",
        continuous=ObservedResultsContinuous(
            control_mean=10.0,
            control_std=2.0,
            control_n=500,
            treatment_mean=11.0,
            treatment_std=2.1,
            treatment_n=500,
        ),
    )
    estimate = estimate_results_cost(request)
    assert estimate.lane == "cheap"


def test_admission_rejects_when_heavy_slots_full() -> None:
    controller = ComputeAdmissionController(
        enabled=True,
        max_heavy_concurrent=1,
        max_cheap_concurrent=8,
        max_cost_units_in_flight=100,
        acquire_timeout_seconds=0.0,
        retry_after_seconds=3,
    )
    heavy = CostEstimate(cost_units=20, lane="heavy", analyzer="bootstrap", n_total=1000, n_resamples=2000)
    with controller.admit(heavy) as first:
        assert first.allowed is True
        with controller.admit(heavy) as second:
            assert second.allowed is False
            assert second.reason == "heavy_concurrency"
            assert second.retry_after_seconds == 3
    snap = controller.snapshot()
    assert snap["rejected"] == 1
    assert snap["heavy_in_flight"] == 0


def test_admission_keeps_cheap_lane_free_when_heavy_full() -> None:
    controller = ComputeAdmissionController(
        enabled=True,
        max_heavy_concurrent=1,
        max_cheap_concurrent=4,
        max_cost_units_in_flight=100,
        acquire_timeout_seconds=0.0,
    )
    heavy = CostEstimate(cost_units=20, lane="heavy", analyzer="quantile")
    cheap = CostEstimate(cost_units=1, lane="cheap", analyzer="binary")
    with controller.admit(heavy) as heavy_decision:
        assert heavy_decision.allowed is True
        with controller.admit(cheap) as cheap_decision:
            assert cheap_decision.allowed is True


def test_admission_rejects_when_cost_budget_exceeded() -> None:
    controller = ComputeAdmissionController(
        enabled=True,
        max_heavy_concurrent=4,
        max_cheap_concurrent=8,
        max_cost_units_in_flight=25,
        acquire_timeout_seconds=0.0,
    )
    heavy = CostEstimate(cost_units=20, lane="heavy", analyzer="bootstrap")
    with controller.admit(heavy) as first:
        assert first.allowed is True
        with controller.admit(heavy) as second:
            assert second.allowed is False
            assert second.reason == "cost_budget"


def test_parallel_expensive_results_exceed_concurrency_budget(monkeypatch) -> None:
    """When the heavy lane is already held, another expensive /results gets 429 + Retry-After."""
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("AB_DB_PATH", str(temp_dir / f"{uuid.uuid4()}.sqlite3"))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    monkeypatch.setenv("AB_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("AB_COMPUTE_ADMISSION_ENABLED", "true")
    monkeypatch.setenv("AB_COMPUTE_MAX_HEAVY_CONCURRENT", "1")
    monkeypatch.setenv("AB_COMPUTE_MAX_COST_UNITS_IN_FLIGHT", "200")
    monkeypatch.setenv("AB_COMPUTE_ACQUIRE_TIMEOUT_MS", "0")
    monkeypatch.setenv("AB_COMPUTE_RETRY_AFTER_SECONDS", "4")
    get_settings.cache_clear()

    control = [float(i) for i in range(200)]
    treatment = [float(i) + 1.0 for i in range(200)]
    payload = {
        "metric_type": "bootstrap",
        "ranked": {"control_values": control, "treatment_values": treatment, "alpha": 0.05},
    }

    with TestClient(create_app()) as client:
        controller = client.app.state.compute_admission
        heavy = CostEstimate(
            cost_units=20, lane="heavy", analyzer="bootstrap", n_total=400, n_resamples=2000
        )
        with controller.admit(heavy) as held:
            assert held.allowed is True
            rejected = client.post("/api/v1/results", json=payload)

    assert rejected.status_code == 429
    body = rejected.json()
    assert body["error_code"] == "compute_capacity_exceeded"
    assert int(rejected.headers["retry-after"]) >= 1
    get_settings.cache_clear()


def test_cheap_results_still_work_when_heavy_lane_busy(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("AB_DB_PATH", str(temp_dir / f"{uuid.uuid4()}.sqlite3"))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    monkeypatch.setenv("AB_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("AB_COMPUTE_MAX_HEAVY_CONCURRENT", "1")
    monkeypatch.setenv("AB_COMPUTE_ACQUIRE_TIMEOUT_MS", "0")
    get_settings.cache_clear()

    cheap_payload = {
        "metric_type": "binary",
        "binary": {
            "control_conversions": 50,
            "control_users": 1000,
            "treatment_conversions": 60,
            "treatment_users": 1000,
        },
    }

    with TestClient(create_app()) as client:
        controller = client.app.state.compute_admission
        heavy = CostEstimate(cost_units=20, lane="heavy", analyzer="bootstrap")
        with controller.admit(heavy) as held:
            assert held.allowed is True
            cheap = client.post("/api/v1/results", json=cheap_payload)

    assert cheap.status_code == 200
    assert cheap.json()["metric_type"] == "binary"
    get_settings.cache_clear()
