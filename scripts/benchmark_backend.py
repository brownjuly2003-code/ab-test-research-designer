from __future__ import annotations

import argparse
from statistics import mean
import sys
from time import perf_counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

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
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * ratio))))
    return ordered[index]


def run_benchmark(payload_name: str, iterations: int) -> dict[str, float]:
    durations_ms: list[float] = []
    payload = PAYLOADS[payload_name]

    for _ in range(iterations):
        start = perf_counter()
        calculate_experiment_metrics(payload)
        durations_ms.append((perf_counter() - start) * 1000)

    return {
        "mean_ms": mean(durations_ms),
        "p95_ms": percentile(durations_ms, 0.95),
        "max_ms": max(durations_ms),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark deterministic backend calculations.")
    parser.add_argument(
        "--payload",
        choices=sorted(PAYLOADS),
        default="binary",
        help="Which payload shape to benchmark.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=500,
        help="How many calculation iterations to run.",
    )
    parser.add_argument(
        "--assert-ms",
        type=float,
        default=None,
        help="Optional upper bound for p95 latency in milliseconds.",
    )
    args = parser.parse_args()

    summary = run_benchmark(args.payload, args.iterations)
    print(
        f"payload={args.payload} iterations={args.iterations} "
        f"mean_ms={summary['mean_ms']:.3f} p95_ms={summary['p95_ms']:.3f} max_ms={summary['max_ms']:.3f}"
    )

    if args.assert_ms is not None and summary["p95_ms"] > args.assert_ms:
        print(
            f"Benchmark failed: p95 {summary['p95_ms']:.3f}ms exceeded threshold {args.assert_ms:.3f}ms"
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
