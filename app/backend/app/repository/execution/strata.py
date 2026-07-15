"""Post-stratification aggregate rollups."""
from __future__ import annotations

from typing import Any

from app.backend.app.constants import (
    BOT_CONVERSION_EVENT_THRESHOLD,
    MAX_STRATA,
)
from app.backend.app.repository._core import _BackendCore


class _StrataRollupMixin(_BackendCore):
    def get_stratified_aggregates(
        self, experiment_id: str, metric_name: str
    ) -> dict[str, Any] | None:
        """Per-(stratum, variation) analysis rollup for post-stratification (F3b).

        Returns ``None`` if the experiment does not exist. Mirrors
        ``get_experiment_analysis_aggregates`` in full — identity resolution (anonymous→canonical
        fold, first-exposure-wins), the manual deny-list, and the experiment-global rate-spike filter
        — then additionally inner-joins each resolved exposed user onto their recorded ``user_strata``
        row (also identity-resolved) and groups by (stratum, variation): users without a stratum are
        excluded (they cannot be placed in a stratum), and the holdout tail (``variation_index = -1``)
        is excluded. Applying the same resolution and exclusion as the primary rollup keeps
        ``stratified_users_total`` a subset of ``exposed_users_total`` by construction — the gap is
        only ever "no stratum recorded," which is what the live-stats copy says. Per (stratum,
        variation) it returns the same shape the main rollup yields per variation — ``exposed_users``,
        ``converted_users``, ``value_sum``, ``value_sq_sum`` — so the service can reuse the binary /
        continuous moment helpers. ``too_many_strata`` flags the pathological case of more than
        ``MAX_STRATA`` distinct strata (the rollup is then skipped).
        """
        with self._connect() as connection:
            if not self._project_exists(connection, experiment_id):
                return None
            stratum_rows = connection.execute(
                """
                SELECT DISTINCT stratum
                FROM user_strata
                WHERE experiment_id = ?
                ORDER BY stratum
                """,
                (experiment_id,),
            ).fetchall()
            strata = [str(row["stratum"]) for row in stratum_rows]
            if len(strata) > MAX_STRATA:
                return {
                    "experiment_id": experiment_id,
                    "metric_name": metric_name,
                    "strata": [],
                    "num_strata": len(strata),
                    "too_many_strata": True,
                }
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
                strata_resolved AS (
                    SELECT DISTINCT
                        COALESCE(im.canonical_id, s.user_id) AS cuser,
                        s.stratum AS stratum
                    FROM user_strata s
                    LEFT JOIN identity_map im
                        ON im.experiment_id = s.experiment_id
                        AND im.anonymous_id = s.user_id
                    WHERE s.experiment_id = ?
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
                    SELECT cuser, SUM(value) AS user_value
                    FROM conv_resolved
                    GROUP BY cuser
                ),
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
                ),
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
                """,
                (
                    experiment_id,
                    experiment_id,
                    experiment_id,
                    metric_name,
                    experiment_id,
                    BOT_CONVERSION_EVENT_THRESHOLD,
                    experiment_id,
                ),
            ).fetchall()
        by_stratum: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_stratum.setdefault(str(row["stratum"]), []).append(
                {
                    "variation_index": int(row["variation_index"]),
                    "exposed_users": int(row["exposed_users"]),
                    "converted_users": int(row["converted_users"] or 0),
                    "value_sum": float(row["value_sum"] or 0.0),
                    "value_sq_sum": float(row["value_sq_sum"] or 0.0),
                }
            )
        strata_payload = [
            {"stratum": stratum, "variations": by_stratum.get(stratum, [])} for stratum in strata
        ]
        return {
            "experiment_id": experiment_id,
            "metric_name": metric_name,
            "strata": strata_payload,
            "num_strata": len(strata),
        }
