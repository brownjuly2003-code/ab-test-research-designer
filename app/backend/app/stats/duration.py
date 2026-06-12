from math import ceil


def estimate_experiment_duration_days(
    sample_size_per_variant: int,
    expected_daily_traffic: int,
    audience_share_in_test: float,
    traffic_split: list[int],
    traffic_allocation_fraction: float = 1.0,
) -> dict:
    if sample_size_per_variant <= 0:
        raise ValueError("sample_size_per_variant must be positive")
    if expected_daily_traffic <= 0:
        raise ValueError("expected_daily_traffic must be positive")
    if not 0 < audience_share_in_test <= 1:
        raise ValueError("audience_share_in_test must be between 0 and 1")
    if not traffic_split or any(weight <= 0 for weight in traffic_split):
        raise ValueError("traffic_split must contain positive values")
    if not 0 < traffic_allocation_fraction <= 1:
        raise ValueError("traffic_allocation_fraction must be between 0 (exclusive) and 1")

    total_weight = sum(traffic_split)
    effective_daily_traffic = expected_daily_traffic * audience_share_in_test
    # A global holdout and/or mutually-exclusive experiments reduce the share of
    # effective traffic this experiment actually receives; sample size is unchanged
    # but accrual is slower, so only the duration grows.
    allocated_daily_traffic = effective_daily_traffic * traffic_allocation_fraction
    slowest_variant_share = min(traffic_split) / total_weight
    daily_traffic_for_smallest_variant = allocated_daily_traffic * slowest_variant_share

    if daily_traffic_for_smallest_variant <= 0:
        raise ValueError("daily traffic for the smallest variant must be positive")

    return {
        "effective_daily_traffic": effective_daily_traffic,
        "allocated_daily_traffic": allocated_daily_traffic,
        "daily_traffic_smallest_variant": daily_traffic_for_smallest_variant,
        "estimated_duration_days": ceil(
            sample_size_per_variant / daily_traffic_for_smallest_variant
        ),
    }
