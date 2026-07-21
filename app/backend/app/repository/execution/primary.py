"""Primary per-arm analysis aggregates over exposures/conversions."""
from __future__ import annotations

from typing import Any

from app.backend.app.constants import (
    BOT_CONVERSION_EVENT_THRESHOLD,
)
from app.backend.app.repository._core import _BackendCore


class _PrimaryRollupMixin(_BackendCore):
    def get_experiment_analysis_aggregates(
        self, experiment_id: str, metric_name: str
    ) -> dict[str, Any] | None:
        """Per-variation analysis-ready rollup for one metric — the input Phase D's live
        SRM / frequentist / Bayesian reads build on.

        Returns ``None`` if the experiment does not exist. A single CTE rolls events up to
        one row per (variation, user) first, then aggregates per variation, so a user with
        several conversion events still counts once for the binary rate and contributes the
        *sum* of their values to the continuous rollup. The holdout tail
        (``variation_index = -1``) is excluded — it is not part of the experiment arms.

        Per variation:
        - ``exposed_users``   — distinct exposed users (dedup is already enforced by the
          ``UNIQUE(experiment_id, user_id)`` exposure constraint).
        - ``converted_users`` — users with at least one conversion on ``metric_name``
          (binary conversion rate numerator).
        - ``value_sum`` / ``value_sq_sum`` — sum and sum-of-squares of per-user value totals
          across *all* exposed users (non-converters contribute 0), so a continuous mean is
          ``value_sum / exposed_users`` and the sample variance is
          ``(value_sq_sum - exposed_users * mean**2) / (exposed_users - 1)``.

        Identity resolution (P4.3): each exposure and conversion is folded onto its canonical id via
        ``identity_map`` (``COALESCE(canonical_id, user_id)``), so a person exposed while anonymous and
        re-exposed / converting after login counts once. A canonical user with several resolved
        exposures keeps the variation of their *first* exposure (lowest ``occurred_at || created_at ||
        id``) — first-exposure-wins, mirroring the sticky exposure store — and the later exposures are
        collapsed (this is the SRM-inflation fix). When ``identity_map`` has no rows the resolution is
        the identity function and this rollup is byte-identical to the unresolved one (no window
        functions; portable on both backends).

        Bot / fraud filter (P4.4): canonical users on the manual deny-list (``excluded_users``, resolved
        to canonical) are removed via a ``NOT EXISTS``-style anti-join. Rate-spike users — more than
        ``BOT_CONVERSION_EVENT_THRESHOLD`` conversion events — are computed **once across all of the
        experiment's metrics**, not just ``metric_name``: a bot is a property of the user, not of one
        metric's event stream, so this call and every other metric's call to this same function (a
        guardrail, for instance) exclude exactly the same set of users and report the same
        ``exposed_users`` for a given arm. When the deny-list is empty and no user trips the threshold
        on any metric the rollup is unchanged. The exclusion is a read-time filter — the raw events are
        never deleted — and the filtered count is surfaced in the live-stats indicator.
        """
        with self._transaction() as connection:
            if not self._project_exists(connection, experiment_id):
                return None
            rows = connection.execute(
                """
                WITH exp_resolved AS (
                    SELECT
                        e.variation_index AS variation_index,
                        COALESCE(im.canonical_id, e.user_id) AS cuser,
                        (e.occurred_at || '|' || e.created_at || '|' || e.id) AS order_key
                    FROM exposures e
                    LEFT JOIN identity_map im
                        ON im.experiment_id = e.experiment_id
                        AND im.anonymous_id = e.user_id
                    WHERE e.experiment_id = ? AND e.variation_index >= 0
                ),
                exp_first AS (
                    SELECT cuser, MIN(order_key) AS order_key
                    FROM exp_resolved
                    GROUP BY cuser
                ),
                arm AS (
                    SELECT er.cuser AS cuser, er.variation_index AS variation_index
                    FROM exp_resolved er
                    JOIN exp_first f ON f.cuser = er.cuser AND f.order_key = er.order_key
                ),
                conv_resolved AS (
                    SELECT
                        COALESCE(im.canonical_id, c.user_id) AS cuser,
                        c.value AS value
                    FROM conversions c
                    LEFT JOIN identity_map im
                        ON im.experiment_id = c.experiment_id
                        AND im.anonymous_id = c.user_id
                    WHERE c.experiment_id = ? AND c.metric = ?
                ),
                conv_per_user AS (
                    -- Collapse the per-event conversions to one row per canonical user *before* the
                    -- join to the arms. Joining the per-event ``conv_resolved`` directly made SQLite
                    -- scan it once per arm user (an O(users * conversions) blow-up); pre-aggregating
                    -- gives a one-row-per-user table the planner can hash-join.
                    SELECT cuser, SUM(value) AS user_value
                    FROM conv_resolved
                    GROUP BY cuser
                ),
                conv_all_resolved AS (
                    -- Rate-spike detection reads across *every* metric, not just ``metric_name`` — a
                    -- bot spamming only one metric must still be excluded from every other metric's
                    -- rollup (guardrails included), or the same arm reports a different N depending on
                    -- which metric happens to have caught the spike.
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
                ),
                user_values AS (
                    -- Deny-list and rate-spike users are both removed with a LEFT JOIN ... IS NULL
                    -- anti-join, materialized once each. ``converted`` is 1 when the user has any
                    -- conversion on *this* metric (``conv_per_user`` row present); a non-converter
                    -- contributes value 0.
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
                """,
                (
                    experiment_id,
                    experiment_id,
                    metric_name,
                    experiment_id,
                    BOT_CONVERSION_EVENT_THRESHOLD,
                    experiment_id,
                ),
            ).fetchall()
        variations = [
            {
                "variation_index": int(row["variation_index"]),
                "exposed_users": int(row["exposed_users"]),
                "converted_users": int(row["converted_users"] or 0),
                "value_sum": float(row["value_sum"] or 0.0),
                "value_sq_sum": float(row["value_sq_sum"] or 0.0),
            }
            for row in rows
        ]
        return {
            "experiment_id": experiment_id,
            "metric_name": metric_name,
            "variations": variations,
        }
