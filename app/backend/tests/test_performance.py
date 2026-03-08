from copy import deepcopy
from time import perf_counter

import pytest

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
