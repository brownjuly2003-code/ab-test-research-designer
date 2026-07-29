"""Canonical analytical population contract (audit F-02 / plan step 3).

One shared definition of *who is in the analysis* for treated arms, ratio
metrics, CUPED, holdout, strata, and event-timing diagnostics:

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
below so primary, ratio, CUPED, holdout, strata, and timing cannot drift.
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


def ratio_metric_conversion_ctes() -> str:
    """Identity-resolved numerator/denominator sums per canonical user.

    Placeholders: ``experiment_id``, numerator metric, denominator metric, then numerator and
    denominator metric again for the ``y`` / ``x`` conditional sums.
    """
    return """
                conv_resolved AS (
                    SELECT
                        COALESCE(im.canonical_id, c.user_id) AS cuser,
                        c.metric AS metric,
                        c.value AS value
                    FROM conversions c
                    LEFT JOIN identity_map im
                        ON im.experiment_id = c.experiment_id
                        AND im.anonymous_id = c.user_id
                    WHERE c.experiment_id = ? AND c.metric IN (?, ?)
                ),
                conv_per_user AS (
                    SELECT
                        cuser,
                        COALESCE(SUM(CASE WHEN metric = ? THEN value ELSE 0 END), 0) AS y,
                        COALESCE(SUM(CASE WHEN metric = ? THEN value ELSE 0 END), 0) AS x
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


def covariate_resolution_ctes() -> str:
    """Identity-resolved covariates; a conflict omits that (user, name).

    Placeholder: one ``experiment_id``.

    One-hop fold via ``identity_map``. Per ``(cuser, covariate_name)``, keep exactly one value
    when all folded raw rows share the same SQL REAL value. If distinct values conflict, omit
    that covariate for the user. Equal duplicates contribute once; complete-case CUPED then
    drops any user missing a discovered covariate after this fold.
    """
    return """
                cov_resolved AS (
                    SELECT
                        COALESCE(im.canonical_id, p.user_id) AS cuser,
                        p.covariate_name AS covariate_name,
                        p.value AS value
                    FROM pre_period_covariates p
                    LEFT JOIN identity_map im
                        ON im.experiment_id = p.experiment_id
                        AND im.anonymous_id = p.user_id
                    WHERE p.experiment_id = ?
                ),
                user_cov AS (
                    SELECT
                        cuser,
                        covariate_name,
                        MIN(value) AS value
                    FROM cov_resolved
                    GROUP BY cuser, covariate_name
                    HAVING COUNT(DISTINCT value) = 1
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
                ),
                arm_means AS (
                    SELECT
                        variation_index,
                        SUM(user_value) * 1.0 / COUNT(*) AS mean_value
                    FROM user_values
                    GROUP BY variation_index
                )
                SELECT
                    uv.variation_index AS variation_index,
                    COUNT(*) AS exposed_users,
                    SUM(uv.converted) AS converted_users,
                    SUM(uv.user_value) AS value_sum,
                    SUM(uv.user_value * uv.user_value) AS value_sq_sum,
                    SUM(
                        (uv.user_value - am.mean_value) * (uv.user_value - am.mean_value)
                    ) AS value_centered_ss
                FROM user_values uv
                JOIN arm_means am ON am.variation_index = uv.variation_index
                GROUP BY uv.variation_index
                ORDER BY uv.variation_index
    """


def ratio_aggregate_sql() -> str:
    """Per-variation ratio sufficient statistics over the treated analytical population."""
    return f"""
                WITH
                {arm_resolution_ctes(ARM_PREDICATE_TREATED)},
                {ratio_metric_conversion_ctes()},
                {exclusion_ctes()},
                user_pairs AS (
                    SELECT
                        arm.variation_index AS variation_index,
                        arm.cuser AS cuser,
                        COALESCE(cpu.y, 0) AS y,
                        COALESCE(cpu.x, 0) AS x
                    FROM arm
                    LEFT JOIN conv_per_user cpu ON cpu.cuser = arm.cuser
                    LEFT JOIN excluded ex ON ex.cuser = arm.cuser
                    LEFT JOIN spike sp ON sp.cuser = arm.cuser
                    WHERE ex.cuser IS NULL AND sp.cuser IS NULL
                ),
                arm_means AS (
                    SELECT
                        variation_index,
                        SUM(x) * 1.0 / COUNT(*) AS mean_x,
                        SUM(y) * 1.0 / COUNT(*) AS mean_y
                    FROM user_pairs
                    GROUP BY variation_index
                )
                SELECT
                    up.variation_index AS variation_index,
                    COUNT(*) AS n,
                    SUM(up.x) AS sum_x,
                    SUM(up.x * up.x) AS sum_x2,
                    SUM(up.y) AS sum_y,
                    SUM(up.y * up.y) AS sum_y2,
                    SUM(up.x * up.y) AS sum_xy,
                    SUM((up.x - am.mean_x) * (up.x - am.mean_x)) AS centered_sxx,
                    SUM((up.y - am.mean_y) * (up.y - am.mean_y)) AS centered_syy,
                    SUM((up.x - am.mean_x) * (up.y - am.mean_y)) AS centered_sxy
                FROM user_pairs up
                JOIN arm_means am ON am.variation_index = up.variation_index
                GROUP BY up.variation_index
                ORDER BY up.variation_index
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
                ),
                holdout_mean AS (
                    SELECT
                        SUM(user_value) * 1.0 / COUNT(*) AS mean_value
                    FROM user_values
                )
                SELECT
                    COUNT(*) AS exposed_users,
                    SUM(uv.converted) AS converted_users,
                    SUM(uv.user_value) AS value_sum,
                    SUM(uv.user_value * uv.user_value) AS value_sq_sum,
                    SUM(
                        (uv.user_value - hm.mean_value) * (uv.user_value - hm.mean_value)
                    ) AS value_centered_ss
                FROM user_values uv
                CROSS JOIN holdout_mean hm
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
                ),
                cell_means AS (
                    SELECT
                        stratum,
                        variation_index,
                        SUM(user_value) * 1.0 / COUNT(*) AS mean_value
                    FROM user_values
                    GROUP BY stratum, variation_index
                )
                SELECT
                    uv.stratum AS stratum,
                    uv.variation_index AS variation_index,
                    COUNT(*) AS exposed_users,
                    SUM(uv.converted) AS converted_users,
                    SUM(uv.user_value) AS value_sum,
                    SUM(uv.user_value * uv.user_value) AS value_sq_sum,
                    SUM(
                        (uv.user_value - cm.mean_value) * (uv.user_value - cm.mean_value)
                    ) AS value_centered_ss
                FROM user_values uv
                JOIN cell_means cm
                    ON cm.stratum = uv.stratum
                    AND cm.variation_index = uv.variation_index
                GROUP BY uv.stratum, uv.variation_index
                ORDER BY uv.stratum, uv.variation_index
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


def ratio_query_params(
    experiment_id: str,
    numerator_metric: str,
    denominator_metric: str,
) -> tuple[object, ...]:
    """Placeholder order for ratio SQL (arm + dual metric + exclusions)."""
    return (
        experiment_id,
        experiment_id,
        numerator_metric,
        denominator_metric,
        numerator_metric,
        denominator_metric,
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


def cuped_query_params(
    experiment_id: str, metric_name: str, covariate_count: int
) -> tuple[object, ...]:
    """Placeholder order for CUPED covered CTE (arm + metric + exclusions + cov + k)."""
    return (
        experiment_id,
        experiment_id,
        metric_name,
        experiment_id,
        BOT_CONVERSION_EVENT_THRESHOLD,
        experiment_id,
        experiment_id,
        covariate_count,
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
