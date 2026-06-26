import uuid
from copy import deepcopy
from pathlib import Path
from time import perf_counter

import pytest

from app.backend.app.repository import ProjectRepository
from app.backend.app.services.calculations_service import calculate_experiment_metrics

PAYLOADS = {
    "binary": {
        "metric_type": "binary",
        "baseline_value": 0.042,
        "mde_pct": 5,
        "alpha": 0.05,
        "power": 0.8,
        "expected_daily_traffic": 12000,
        "audience_share_in_test": 0.6,
        "traffic_split": [50, 50],
        "variants_count": 2,
        "seasonality_present": True,
        "active_campaigns_present": False,
        "long_test_possible": True,
    },
    "continuous": {
        "metric_type": "continuous",
        "baseline_value": 15.0,
        "std_dev": 12.0,
        "mde_pct": 5,
        "alpha": 0.05,
        "power": 0.8,
        "expected_daily_traffic": 8000,
        "audience_share_in_test": 0.5,
        "traffic_split": [50, 50],
        "variants_count": 2,
        "seasonality_present": False,
        "active_campaigns_present": False,
        "long_test_possible": True,
    },
}


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * ratio))))
    return ordered[index]


def benchmark_payload(payload: dict, iterations: int = 200) -> float:
    calculate_experiment_metrics(deepcopy(payload))
    durations_ms: list[float] = []

    for _ in range(iterations):
        start = perf_counter()
        calculate_experiment_metrics(deepcopy(payload))
        durations_ms.append((perf_counter() - start) * 1000)

    return percentile(durations_ms, 0.95)


@pytest.mark.parametrize("payload_name", ["binary", "continuous"])
def test_calculation_p95_latency_stays_below_100ms(payload_name: str) -> None:
    p95_ms = benchmark_payload(PAYLOADS[payload_name])

    assert p95_ms < 100, f"{payload_name} calculation p95 was {p95_ms:.3f}ms"


def _scale_repo(tmp_path: Path) -> tuple[ProjectRepository, str]:
    repo = ProjectRepository(str(tmp_path / f"{uuid.uuid4()}.sqlite3"))
    project = repo.create_project(
        {
            "project": {"project_name": "Scale"},
            "hypothesis": {},
            "setup": {},
            "metrics": {},
            "constraints": {},
            "additional_context": {},
        }
    )
    exp = project["id"]
    n = 2000
    repo.record_exposures(exp, [{"user_id": f"u{i}", "variation_index": i % 2} for i in range(n)])
    repo.record_conversions(
        exp,
        [
            {"user_id": f"u{i}", "metric": "purchase", "value": 1.0, "idempotency_key": f"p{i}"}
            for i in range(n)
            if i % 5 != 0
        ],
    )
    repo.record_pre_period_values(
        exp,
        [
            {"user_id": f"u{i}", "covariate_name": f"c{c}", "value": float((i * (c + 1)) % 97)}
            for i in range(n)
            for c in range(2)
        ],
    )
    return repo, exp


def test_live_read_rollups_stay_well_under_a_second_at_scale(tmp_path: Path) -> None:
    """Guards the live-read indexing/structure: both the primary rollup and the (heaviest)
    multi-covariate CUPED rollup must stay fast at 2000 users. Before the
    ``conversions(experiment_id, user_id, metric)`` index and the per-user pre-aggregation of the
    primary rollup these were multi-second (CUPED ~4s, the primary rollup quadratic); the 2.0s
    ceiling has a large margin over the optimized path (~0.1s) while still failing loudly on a
    regression to the per-user-scan / unindexed-join behavior.
    """
    repo, exp = _scale_repo(tmp_path)

    # Warm once (table/index stats), then take the best of three.
    repo.get_experiment_analysis_aggregates(exp, "purchase")
    repo.get_cuped_aggregates(exp, "purchase")

    def _best(fn, *args: object) -> float:
        samples = []
        for _ in range(3):
            start = perf_counter()
            fn(*args)
            samples.append(perf_counter() - start)
        return min(samples)

    primary_s = _best(repo.get_experiment_analysis_aggregates, exp, "purchase")
    cuped_s = _best(repo.get_cuped_aggregates, exp, "purchase")

    assert primary_s < 2.0, f"primary rollup took {primary_s * 1000:.0f}ms at 2000 users"
    assert cuped_s < 2.0, f"CUPED rollup took {cuped_s * 1000:.0f}ms at 2000 users"
