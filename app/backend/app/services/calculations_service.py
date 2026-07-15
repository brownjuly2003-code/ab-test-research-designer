import math
from typing import Any

from app.backend.app.constants import MAX_SUPPORTED_VARIANTS
from app.backend.app.metric_capabilities import requires_std_dev_for_planning
from app.backend.app.rules.engine import evaluate_warnings
from app.backend.app.stats.bayesian import (
    bayesian_sample_size_binary,
    bayesian_sample_size_continuous,
)
from app.backend.app.stats.binary import calculate_binary_sample_size
from app.backend.app.stats.cluster import inflate_for_cluster_design
from app.backend.app.stats.continuous import (
    calculate_continuous_sample_size,
    calculate_cuped_theta,
    calculate_cuped_variance_reduction,
)
from app.backend.app.stats.duration import estimate_experiment_duration_days
from app.backend.app.stats.equivalence import calculate_tost_sample_size
from app.backend.app.stats.fisher_exact import calculate_fisher_exact_sample_size
from app.backend.app.stats.mann_whitney import calculate_mann_whitney_sample_size
from app.backend.app.stats.poisson_rate import calculate_poisson_rate_sample_size
from app.backend.app.stats.sequential import (
    obrien_fleming_boundaries,
    sequential_sample_size_inflation,
)


def _validate_variant_configuration(variants_count: int, traffic_split: list[int]) -> None:
    if not 2 <= variants_count <= MAX_SUPPORTED_VARIANTS:
        raise ValueError(f"variants_count must be between 2 and {MAX_SUPPORTED_VARIANTS}")
    if len(traffic_split) != variants_count:
        raise ValueError("traffic_split length must match variants_count")


def _build_bonferroni_note(variants_count: int, adjusted_alpha: float | None) -> str | None:
    if variants_count <= 2 or adjusted_alpha is None:
        return None

    comparison_count = max(1, variants_count - 1)
    return (
        f"Bonferroni correction is applied across {comparison_count} treatment-vs-control comparisons "
        f"with adjusted alpha {adjusted_alpha:.6g}. Consider a less conservative correction if the design "
        "becomes impractically large."
    )


# Default planned analysis per metric type when the request does not name one. "z_test" is the
# historical normal-approximation path (binary two-proportion z; continuous/ratio mean z formula);
# count metrics have exactly one plan (the conditional Poisson rate test).
_DEFAULT_PLANNED_TEST = {
    "binary": "z_test",
    "continuous": "z_test",
    "ratio": "z_test",
    "count": "poisson_rate",
}


def calculate_experiment_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    metric_type = payload["metric_type"]
    variants_count = int(payload.get("variants_count", len(payload["traffic_split"])))
    traffic_split = payload["traffic_split"]
    n_looks = int(payload.get("n_looks", 1))
    planned_test = payload.get("planned_test") or _DEFAULT_PLANNED_TEST.get(metric_type)

    _validate_variant_configuration(variants_count, traffic_split)

    if metric_type == "binary":
        if planned_test == "fisher_exact":
            calculation_summary = calculate_fisher_exact_sample_size(
                baseline_rate=payload["baseline_value"],
                mde_pct=payload["mde_pct"],
                alpha=payload["alpha"],
                power=payload["power"],
                variants_count=variants_count,
            )
        elif planned_test == "z_test":
            calculation_summary = calculate_binary_sample_size(
                baseline_rate=payload["baseline_value"],
                mde_pct=payload["mde_pct"],
                alpha=payload["alpha"],
                power=payload["power"],
                variants_count=variants_count,
            )
        else:
            raise ValueError(f"Unsupported planned_test for binary metrics: {planned_test}")
    elif metric_type == "continuous" and planned_test == "mann_whitney":
        if payload.get("std_dev") is None and requires_std_dev_for_planning(metric_type):
            raise ValueError("std_dev must be positive for continuous and ratio metrics")
        calculation_summary = calculate_mann_whitney_sample_size(
            baseline_mean=payload["baseline_value"],
            std_dev=payload["std_dev"],
            mde_pct=payload["mde_pct"],
            alpha=payload["alpha"],
            power=payload["power"],
            variants_count=variants_count,
        )
    elif metric_type == "continuous" and planned_test == "tost":
        if payload.get("std_dev") is None and requires_std_dev_for_planning(metric_type):
            raise ValueError("std_dev must be positive for continuous and ratio metrics")
        if payload.get("equivalence_margin_pct") is None:
            raise ValueError("equivalence_margin_pct is required for a TOST equivalence plan")
        calculation_summary = calculate_tost_sample_size(
            baseline_mean=payload["baseline_value"],
            std_dev=payload["std_dev"],
            equivalence_margin_pct=payload["equivalence_margin_pct"],
            alpha=payload["alpha"],
            power=payload["power"],
            variants_count=variants_count,
        )
        # An equivalence plan is driven by the margin, not the MDE (the assumptions say so), but
        # the summary still echoes the user's MDE fields for a uniform response shape.
        calculation_summary["mde_pct"] = payload["mde_pct"]
        calculation_summary["mde_absolute"] = payload["baseline_value"] * (payload["mde_pct"] / 100)
    elif metric_type in ("continuous", "ratio"):
        if planned_test != "z_test":
            raise ValueError(f"Unsupported planned_test for {metric_type} metrics: {planned_test}")
        if payload.get("std_dev") is None and requires_std_dev_for_planning(metric_type):
            raise ValueError("std_dev must be positive for continuous and ratio metrics")
        calculation_summary = calculate_continuous_sample_size(
            baseline_mean=payload["baseline_value"],
            std_dev=payload["std_dev"],
            mde_pct=payload["mde_pct"],
            alpha=payload["alpha"],
            power=payload["power"],
            variants_count=variants_count,
        )
        if metric_type == "ratio":
            # A ratio metric R = E[Y]/E[X] is sized by the delta method: the per-user linearized value
            # (numerator - R*denominator) is the continuous analysis unit, with mean R (baseline_value)
            # and the supplied per-user standard deviation, so the two-sample continuous sample-size
            # formula applies unchanged. Restamp the metric identity and the lead assumption the
            # continuous calculator returned.
            calculation_summary["metric_type"] = "ratio"
            calculation_summary["assumptions"] = [
                "Ratio metric sized by the delta method: the per-user value "
                "(numerator - R x denominator) is the analysis unit, with baseline ratio R and the "
                "supplied per-user standard deviation.",
                *calculation_summary["assumptions"][1:],
            ]
    elif metric_type == "count":
        # Reachable today at the service level (the wizard/schema count metric type is the 2.2
        # increment); sized through the same conditional framing the Poisson rate analyzer uses.
        if planned_test != "poisson_rate":
            raise ValueError(f"Unsupported planned_test for count metrics: {planned_test}")
        calculation_summary = calculate_poisson_rate_sample_size(
            baseline_rate=payload["baseline_value"],
            mde_pct=payload["mde_pct"],
            alpha=payload["alpha"],
            power=payload["power"],
            exposure_per_user=payload.get("exposure_per_user") or 1.0,
            variants_count=variants_count,
        )
    else:
        raise ValueError(f"Unsupported metric_type: {metric_type}")

    # Cluster-randomized design effect (P5.2). When the randomization unit is a cluster and the
    # average cluster size + ICC are supplied, inflate the individual-level per-arm sample size by
    # the Kish design effect DEFF = 1 + (m - 1)*ICC (Donner & Klar 2000; Hayes & Moulton 2009).
    # Applied to the primary plan here — and, further down, to the CUPED and Bayesian companions —
    # so every reported per-arm size reflects the design; it degenerates to the individual-level
    # path exactly at ICC=0 or m=1. The duration below is computed from the inflated size, and the
    # sequential block reuses it, so both stack correctly for free. The deterministic
    # CLUSTER_RANDOMIZATION warning still fires: sizing accounts for clustering, but the live
    # analysis still uses naive SEs (cluster-robust analysis is a separate future increment).
    avg_cluster_size = payload.get("avg_cluster_size")
    icc = payload.get("icc")
    cluster_design = (
        payload.get("randomization_unit") == "cluster"
        and avg_cluster_size is not None
        and icc is not None
    )
    design_effect: float | None = None
    clusters_per_variant: int | None = None
    if cluster_design and avg_cluster_size is not None and icc is not None:
        cluster = inflate_for_cluster_design(
            individual_sample_size_per_variant=calculation_summary["sample_size_per_variant"],
            avg_cluster_size=avg_cluster_size,
            icc=icc,
            variants_count=variants_count,
        )
        design_effect = cluster["design_effect"]
        clusters_per_variant = cluster["clusters_per_variant"]
        calculation_summary["sample_size_per_variant"] = cluster["sample_size_per_variant"]
        calculation_summary["total_sample_size"] = cluster["total_sample_size"]
        calculation_summary["assumptions"] = [
            *calculation_summary["assumptions"],
            (
                "Cluster-randomized design: the individual-level sample size is inflated by the Kish "
                f"design effect DEFF = 1 + (m - 1) x ICC = {design_effect:.4g} "
                f"(m = {avg_cluster_size:g} individuals per cluster, ICC = {icc:g}), requiring about "
                f"{clusters_per_variant:,} clusters per arm (Donner & Klar 2000; Hayes & Moulton 2009)."
            ),
            (
                "Cluster sizes are assumed equal; unequal cluster sizes inflate the true design effect "
                "further (Eldridge & Kerry's coefficient-of-variation correction is out of scope here)."
            ),
            (
                "The design effect adjusts the planned sample size only; the live analysis still uses "
                "naive standard errors, and valid cluster inference needs enough clusters per arm."
            ),
        ]

    holdout_fraction = payload.get("holdout_fraction")
    mutually_exclusive_experiments = payload.get("mutually_exclusive_experiments")
    holdout = float(holdout_fraction) if holdout_fraction is not None else 0.0
    me_count = int(mutually_exclusive_experiments) if mutually_exclusive_experiments is not None else 1
    traffic_allocation_fraction = (1.0 - holdout) / me_count
    has_traffic_allocation = holdout_fraction is not None or mutually_exclusive_experiments is not None

    duration = estimate_experiment_duration_days(
        sample_size_per_variant=calculation_summary["sample_size_per_variant"],
        expected_daily_traffic=payload["expected_daily_traffic"],
        audience_share_in_test=payload["audience_share_in_test"],
        traffic_split=traffic_split,
        traffic_allocation_fraction=traffic_allocation_fraction,
    )

    result = {
        "calculation_summary": {
            "metric_type": calculation_summary["metric_type"],
            "baseline_value": calculation_summary["baseline_value"],
            "mde_pct": calculation_summary["mde_pct"],
            "mde_absolute": calculation_summary["mde_absolute"],
            "alpha": calculation_summary["alpha"],
            "power": calculation_summary["power"],
            "planned_test": planned_test,
            "equivalence_margin_pct": calculation_summary.get("equivalence_margin_pct"),
            "equivalence_margin_absolute": calculation_summary.get("equivalence_margin_absolute"),
        },
        "results": {
            "sample_size_per_variant": calculation_summary["sample_size_per_variant"],
            "total_sample_size": calculation_summary["total_sample_size"],
            "effective_daily_traffic": duration["effective_daily_traffic"],
            "estimated_duration_days": duration["estimated_duration_days"],
            "holdout_fraction": holdout_fraction,
            "mutually_exclusive_experiments": mutually_exclusive_experiments,
            "allocated_daily_traffic": (
                duration["allocated_daily_traffic"] if has_traffic_allocation else None
            ),
        },
        "assumptions": calculation_summary["assumptions"],
        "warnings": [],
        "bonferroni_note": _build_bonferroni_note(
            variants_count,
            calculation_summary.get("adjusted_alpha"),
        ),
        "design_effect": round(design_effect, 4) if design_effect is not None else None,
        "avg_cluster_size": avg_cluster_size if cluster_design else None,
        "icc": icc if cluster_design else None,
        "clusters_per_variant": clusters_per_variant,
        "bayesian_sample_size_per_variant": None,
        "bayesian_credibility": None,
        "bayesian_note": None,
        "sequential_boundaries": None,
        "sequential_inflation_factor": None,
        "sequential_adjusted_sample_size": None,
        "cuped_std": None,
        "cuped_sample_size_per_variant": None,
        "cuped_variance_reduction_pct": None,
        "cuped_duration_days": None,
        "cuped_theta": None,
    }

    # The CUPED companion quantifies variance reduction on the default mean-based plan; its numbers
    # (MDE-driven continuous formula) would be misleading next to a rank or equivalence plan.
    if (
        metric_type == "continuous"
        and planned_test == "z_test"
        and payload.get("cuped_correlation") is not None
        and payload.get("cuped_pre_experiment_std") is not None
    ):
        cuped_std, variance_reduction = calculate_cuped_variance_reduction(
            outcome_std=payload["std_dev"],
            pre_experiment_std=payload["cuped_pre_experiment_std"],
            correlation=payload["cuped_correlation"],
        )
        cuped_summary = calculate_continuous_sample_size(
            baseline_mean=payload["baseline_value"],
            std_dev=cuped_std,
            mde_pct=payload["mde_pct"],
            alpha=payload["alpha"],
            power=payload["power"],
            variants_count=variants_count,
        )
        if cluster_design and avg_cluster_size is not None and icc is not None:
            # The design effect applies to the CUPED-reduced size too; leaving it individual-level
            # next to an inflated primary would understate it.
            cuped_summary["sample_size_per_variant"] = inflate_for_cluster_design(
                individual_sample_size_per_variant=cuped_summary["sample_size_per_variant"],
                avg_cluster_size=avg_cluster_size,
                icc=icc,
                variants_count=variants_count,
            )["sample_size_per_variant"]
        cuped_duration = estimate_experiment_duration_days(
            sample_size_per_variant=cuped_summary["sample_size_per_variant"],
            expected_daily_traffic=payload["expected_daily_traffic"],
            audience_share_in_test=payload["audience_share_in_test"],
            traffic_split=traffic_split,
            traffic_allocation_fraction=traffic_allocation_fraction,
        )
        result["cuped_std"] = round(cuped_std, 4)
        result["cuped_sample_size_per_variant"] = cuped_summary["sample_size_per_variant"]
        result["cuped_variance_reduction_pct"] = round(variance_reduction * 100, 1)
        result["cuped_duration_days"] = float(cuped_duration["estimated_duration_days"])
        result["cuped_theta"] = round(
            calculate_cuped_theta(
                outcome_std=payload["std_dev"],
                pre_experiment_std=payload["cuped_pre_experiment_std"],
                correlation=payload["cuped_correlation"],
            ),
            4,
        )

    # The Bayesian precision companion exists for the proportion/mean estimators only; a count
    # metric has no std_dev to feed the continuous branch (schema-level count arrives with 2.2).
    if (
        payload.get("analysis_mode") == "bayesian"
        and payload.get("desired_precision") is not None
        and metric_type in ("binary", "continuous", "ratio")
    ):
        if metric_type == "binary":
            bayesian_sample_size = bayesian_sample_size_binary(
                baseline_rate=payload["baseline_value"],
                desired_precision=payload["desired_precision"] / 100,
                credibility=payload.get("credibility", 0.95),
            )
            precision_unit = "pp"
        else:
            bayesian_sample_size = bayesian_sample_size_continuous(
                std_dev=payload["std_dev"],
                desired_precision=payload["desired_precision"],
                credibility=payload.get("credibility", 0.95),
            )
            precision_unit = "units"

        if cluster_design and avg_cluster_size is not None and icc is not None:
            # A credible-interval half-width is variance-driven, so the same design effect inflates
            # the Bayesian precision size just like the frequentist one.
            bayesian_sample_size = inflate_for_cluster_design(
                individual_sample_size_per_variant=bayesian_sample_size,
                avg_cluster_size=avg_cluster_size,
                icc=icc,
                variants_count=variants_count,
            )["sample_size_per_variant"]

        result["bayesian_sample_size_per_variant"] = bayesian_sample_size
        result["bayesian_credibility"] = payload.get("credibility", 0.95)
        result["bayesian_note"] = (
            f"Bayesian estimate: N={bayesian_sample_size:,} per variant gives a "
            f"{payload.get('credibility', 0.95) * 100:.0f}% credible interval half-width <= "
            f"{payload['desired_precision']:g} {precision_unit}."
        )

    if n_looks > 1:
        inflation = sequential_sample_size_inflation(
            n_looks=n_looks,
            alpha=payload["alpha"],
            power=payload["power"],
        )
        result["sequential_boundaries"] = obrien_fleming_boundaries(
            n_looks=n_looks,
            alpha=payload["alpha"],
        )
        result["sequential_inflation_factor"] = round(inflation, 4)
        result["sequential_adjusted_sample_size"] = math.ceil(
            calculation_summary["sample_size_per_variant"] * inflation
        )

    result["warnings"] = evaluate_warnings(
        payload=payload,
        results={
            # The low-traffic rules must see the traffic this experiment actually
            # receives after holdout / mutual exclusion (equals effective when neither
            # is set, so the no-allocation path is unchanged).
            "effective_daily_traffic": duration["allocated_daily_traffic"],
            "estimated_duration_days": duration["estimated_duration_days"],
            "sequential_inflation_factor": result["sequential_inflation_factor"],
        },
    )
    return result
