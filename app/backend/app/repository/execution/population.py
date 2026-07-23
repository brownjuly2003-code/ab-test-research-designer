"""Canonical analytical population contract (audit F-02 / plan step 3).

One shared definition of *who is in the analysis* for treated arms, holdout,
strata, and event-timing diagnostics:

- **Identity (one-hop):** ``COALESCE(identity_map.canonical_id, user_id)`` via a
  left join on ``anonymous_id = user_id``. Chains/cycles are rejected at ingest;
  rollups do not walk multi-hop paths.
- **First exposure wins:** among all resolved exposures for a canonical user,
  keep the row with the minimum ``occurred_at | created_at | id`` order key and
  that row's ``variation_index`` / exposure timestamp.
- **Exclusions:** manual deny-list (``excluded_users``, identity-resolved) and
  experiment-global rate-spike (more than ``BOT_CONVERSION_EVENT_THRESHOLD``
  conversion *events* across all metrics). Read-time only — raw events stay.
- **Arm filter:** treated/strata/timing use ``variation_index >= 0``; holdout uses
  ``variation_index = -1``. Same identity + exclusion rules either way.

Do not fork this logic into ad-hoc SQL. Compose queries from the CTE helpers
below so primary, holdout, strata, and timing cannot drift.
"""

from __future__ import annotations

from typing import Final

from app.backend.app.constants import BOT_CONVERSION_EVENT_THRESHOLD

# Bump when the population contract changes in a decision-relevant way.
ANALYTICAL_POPULATION_POLICY_VERSION: Final[str] = "analytical_population_v1"

ARM_PREDICATE_TREATED: Final[str] = "e.variation_index >= 0"
ARM_PREDICATE_HOLDOUT: Final[str] = "e.variation_index = -1"


def arm_resolution_ctes(arm_predicate: str) -> str:
    """Resolve exposures to canonical users and pick first-exposure-wins arm.

    Placeholder: one ``experiment_id`` for the exposures filter.
    """
    return f"""
                exp_resolved AS (
                    SELECT
                        e.variation_index AS variation_index,
                        COALESCE(im.canonical_id, e.user_id) AS cuser,
                        (e.occurred_at || '|' || e.created_at || '|' || e.id) AS order_key,
                        e.occurred_at AS exposure_at
                    FROM exposures e
                    LEFT JOIN identity_map im
                        ON im.experiment_id = e.experiment_id
                        AND im.anonymous_id = e.user_id
                    WHERE e.experiment_id = ? AND {arm_predicate}
                ),
                exp_first AS (
                    SELECT cuser, MIN(order_key) AS order_key
                    FROM exp_resolved
                    GROUP BY cuser
                ),
                arm AS (
                    SELECT
                        er.cuser AS cuser,
                        er.variation_index AS variation_index,
                        er.exposure_at AS exposure_at
                    FROM exp_resolved er
                    JOIN exp_first f ON f.cuser = er.cuser AND f.order_key = er.order_key
                )
    """


def metric_conversion_ctes() -> str:
    """Identity-resolved conversions for one metric + per-user value sum.

    Placeholders: ``experiment_id``, ``metric_name``.
    """
    return """
                conv_resolved AS (
                    SELECT
                        COALESCE(im.canonical_id, c.user_id) AS cuser,
                        c.value AS value,
                        c.occurred_at AS conversion_at
                    FROM conversions c
                    LEFT JOIN identity_map im
                        ON im.experiment_id = c.experiment_id
                        AND im.anonymous_id = c.user_id
                    WHERE c.experiment_id = ? AND c.metric = ?
                ),
                conv_per_user AS (
                    SELECT cuser, SUM(value) AS user_value
                    FROM conv_resolved
                    GROUP BY cuser
                )
    """


def exclusion_ctes() -> str:
    """Experiment-global rate-spike + identity-resolved manual deny-list.

    Placeholders: ``experiment_id``, ``BOT_CONVERSION_EVENT_THRESHOLD``, ``experiment_id``.
    """
    return """
                conv_all_resolved AS (
                    SELECT COALESCE(im.canonical_id, c.user_id) AS cuser
                    FROM conversions c
                    LEFT JOIN identity_map im
                        ON im.experiment_id = c.experiment_id
                        AND im.anonymous_id = c.user_id
                    WHERE c.experiment_id = ?
                ),
                spike AS (
                    SELECT cuser FROM conv_all_resolved GROUP BY cuser HAVING COUNT(*) > ?
                ),
                excluded AS (
                    SELECT DISTINCT COALESCE(im.canonical_id, x.user_id) AS cuser
                    FROM excluded_users x
                    LEFT JOIN identity_map im
                        ON im.experiment_id = x.experiment_id
                        AND im.anonymous_id = x.user_id
                    WHERE x.experiment_id = ?
                )
    """


def strata_resolution_cte() -> str:
    """Identity-resolved user→stratum map. Placeholder: ``experiment_id``."""
    return """
                strata_resolved AS (
                    SELECT DISTINCT
                        COALESCE(im.canonical_id, s.user_id) AS cuser,
                        s.stratum AS stratum
                    FROM user_strata s
                    LEFT JOIN identity_map im
                        ON im.experiment_id = s.experiment_id
                        AND im.anonymous_id = s.user_id
                    WHERE s.experiment_id = ?
                )
    """


def primary_aggregate_sql() -> str:
    """Per-variation treated rollup (``variation_index >= 0``)."""
    return f"""
                WITH
                {arm_resolution_ctes(ARM_PREDICATE_TREATED)},
                {metric_conversion_ctes()},
                {exclusion_ctes()},
                user_values AS (
                    SELECT
                        arm.variation_index AS variation_index,
                        arm.cuser AS cuser,
                        COALESCE(cpu.user_value, 0) AS user_value,
                        CASE WHEN cpu.cuser IS NOT NULL THEN 1 ELSE 0 END AS converted
                    FROM arm
                    LEFT JOIN conv_per_user cpu ON cpu.cuser = arm.cuser
                    LEFT JOIN excluded ex ON ex.cuser = arm.cuser
                    LEFT JOIN spike sp ON sp.cuser = arm.cuser
                    WHERE ex.cuser IS NULL AND sp.cuser IS NULL
                )
                SELECT
                    variation_index,
                    COUNT(*) AS exposed_users,
                    SUM(converted) AS converted_users,
                    SUM(user_value) AS value_sum,
                    SUM(user_value * user_value) AS value_sq_sum
                FROM user_values
                GROUP BY variation_index
                ORDER BY variation_index
    """


def holdout_aggregate_sql() -> str:
    """Single holdout group rollup (``variation_index = -1``), same population rules."""
    return f"""
                WITH
                {arm_resolution_ctes(ARM_PREDICATE_HOLDOUT)},
                {metric_conversion_ctes()},
                {exclusion_ctes()},
                user_values AS (
                    SELECT
                        arm.cuser AS cuser,
                        COALESCE(cpu.user_value, 0) AS user_value,
                        CASE WHEN cpu.cuser IS NOT NULL THEN 1 ELSE 0 END AS converted
                    FROM arm
                    LEFT JOIN conv_per_user cpu ON cpu.cuser = arm.cuser
                    LEFT JOIN excluded ex ON ex.cuser = arm.cuser
                    LEFT JOIN spike sp ON sp.cuser = arm.cuser
                    WHERE ex.cuser IS NULL AND sp.cuser IS NULL
                )
                SELECT
                    COUNT(*) AS exposed_users,
                    SUM(converted) AS converted_users,
                    SUM(user_value) AS value_sum,
                    SUM(user_value * user_value) AS value_sq_sum
                FROM user_values
    """


def stratified_aggregate_sql() -> str:
    """Per-(stratum, variation) treated rollup with shared population rules."""
    return f"""
                WITH
                {arm_resolution_ctes(ARM_PREDICATE_TREATED)},
                {strata_resolution_cte()},
                {metric_conversion_ctes()},
                {exclusion_ctes()},
                user_values AS (
                    SELECT
                        sr.stratum AS stratum,
                        arm.variation_index AS variation_index,
                        arm.cuser AS cuser,
                        COALESCE(cpu.user_value, 0) AS user_value,
                        CASE WHEN cpu.cuser IS NOT NULL THEN 1 ELSE 0 END AS converted
                    FROM arm
                    JOIN strata_resolved sr ON sr.cuser = arm.cuser
                    LEFT JOIN conv_per_user cpu ON cpu.cuser = arm.cuser
                    LEFT JOIN excluded ex ON ex.cuser = arm.cuser
                    LEFT JOIN spike sp ON sp.cuser = arm.cuser
                    WHERE ex.cuser IS NULL AND sp.cuser IS NULL
                )
                SELECT
                    stratum,
                    variation_index,
                    COUNT(*) AS exposed_users,
                    SUM(converted) AS converted_users,
                    SUM(user_value) AS value_sum,
                    SUM(user_value * user_value) AS value_sq_sum
                FROM user_values
                GROUP BY stratum, variation_index
                ORDER BY stratum, variation_index
    """


def event_timing_pairs_sql() -> str:
    """(exposure_at, conversion_at) pairs for treated population, identity-resolved.

    Uses first-exposure timing anchor and the same exclusion filters as primary.
    Counts are over conversion *events* (multiple rows per user possible).
    """
    return f"""
                WITH
                {arm_resolution_ctes(ARM_PREDICATE_TREATED)},
                {metric_conversion_ctes()},
                {exclusion_ctes()}
                SELECT arm.exposure_at AS exposure_at, cr.conversion_at AS conversion_at
                FROM arm
                JOIN conv_resolved cr ON cr.cuser = arm.cuser
                LEFT JOIN excluded ex ON ex.cuser = arm.cuser
                LEFT JOIN spike sp ON sp.cuser = arm.cuser
                WHERE ex.cuser IS NULL AND sp.cuser IS NULL
    """


def population_count_sql(arm_predicate: str) -> str:
    """Count distinct in-population canonical users for one arm filter (no metric)."""
    return f"""
                WITH
                {arm_resolution_ctes(arm_predicate)},
                {exclusion_ctes()}
                SELECT COUNT(*) AS n
                FROM arm
                LEFT JOIN excluded ex ON ex.cuser = arm.cuser
                LEFT JOIN spike sp ON sp.cuser = arm.cuser
                WHERE ex.cuser IS NULL AND sp.cuser IS NULL
    """


def aggregate_query_params(experiment_id: str, metric_name: str) -> tuple[object, ...]:
    """Placeholder order for primary / holdout SQL (arm + metric + exclusions)."""
    return (
        experiment_id,
        experiment_id,
        metric_name,
        experiment_id,
        BOT_CONVERSION_EVENT_THRESHOLD,
        experiment_id,
    )


def stratified_query_params(experiment_id: str, metric_name: str) -> tuple[object, ...]:
    """Placeholder order for stratified SQL (arm + strata + metric + exclusions)."""
    return (
        experiment_id,
        experiment_id,
        experiment_id,
        metric_name,
        experiment_id,
        BOT_CONVERSION_EVENT_THRESHOLD,
        experiment_id,
    )


def population_count_params(experiment_id: str) -> tuple[object, ...]:
    """Placeholder order for population_count_sql (arm + exclusions, no metric)."""
    return (
        experiment_id,
        experiment_id,
        BOT_CONVERSION_EVENT_THRESHOLD,
        experiment_id,
    )


def population_fingerprint(
    *,
    treated_users: int,
    holdout_users: int,
    manual_excluded: int,
    rate_spike_excluded: int,
    linked_identities: int,
    metric_name: str,
) -> str:
    """Stable, human-readable fingerprint for diagnostics / divergence detection."""
    total_excluded = manual_excluded + rate_spike_excluded
    return (
        f"{ANALYTICAL_POPULATION_POLICY_VERSION}"
        f"|metric={metric_name}"
        f"|treated={treated_users}"
        f"|holdout={holdout_users}"
        f"|excluded={total_excluded}"
        f"|manual={manual_excluded}"
        f"|spike={rate_spike_excluded}"
        f"|links={linked_identities}"
    )
