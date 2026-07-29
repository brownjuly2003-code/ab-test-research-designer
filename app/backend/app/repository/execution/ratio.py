"""Ratio-metric sufficient statistics over exposed users."""
from __future__ import annotations

from typing import Any

from app.backend.app.repository._core import _BackendCore


class _RatioRollupMixin(_BackendCore):
    def get_ratio_aggregates(
        self, experiment_id: str, numerator_metric: str, denominator_metric: str
    ) -> dict[str, Any] | None:
        """Per-variation ratio-metric sufficient statistics over the exposed users (F2).

        Returns ``None`` if the experiment does not exist. A ratio metric ``R = sum(Y)/sum(X)`` is
        carried as two ingested conversion metrics — the numerator (e.g. ``clicks``) and the
        denominator (e.g. ``impressions``). Per user this rolls up ``y`` = sum of numerator values
        and ``x`` = sum of denominator values (non-events contribute 0), then per variation the
        delta-method sufficient statistics. Historical raw moment keys remain available, while a
        portable two-pass rollup adds stable ``centered_sxx``, ``centered_syy`` and ``centered_sxy``
        so modest scatter at large means is not lost to cancellation. Every exposed user is the
        analysis unit (Kohavi et al.); the holdout tail (``variation_index = -1``) is excluded.
        """
        with self._transaction() as connection:
            if not self._project_exists(connection, experiment_id):
                return None
            rows = connection.execute(
                """
                WITH user_pairs AS (
                    SELECT
                        e.variation_index AS variation_index,
                        e.user_id AS user_id,
                        COALESCE(SUM(CASE WHEN c.metric = ? THEN c.value ELSE 0 END), 0) AS y,
                        COALESCE(SUM(CASE WHEN c.metric = ? THEN c.value ELSE 0 END), 0) AS x
                    FROM exposures e
                    LEFT JOIN conversions c
                        ON c.experiment_id = e.experiment_id
                        AND c.user_id = e.user_id
                        AND c.metric IN (?, ?)
                    WHERE e.experiment_id = ? AND e.variation_index >= 0
                    GROUP BY e.variation_index, e.user_id
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
                """,
                (
                    numerator_metric,
                    denominator_metric,
                    numerator_metric,
                    denominator_metric,
                    experiment_id,
                ),
            ).fetchall()
        variations = [
            {
                "variation_index": int(row["variation_index"]),
                "n": int(row["n"]),
                "sum_x": float(row["sum_x"] or 0.0),
                "sum_x2": float(row["sum_x2"] or 0.0),
                "sum_y": float(row["sum_y"] or 0.0),
                "sum_y2": float(row["sum_y2"] or 0.0),
                "sum_xy": float(row["sum_xy"] or 0.0),
                "centered_sxx": float(row["centered_sxx"] or 0.0),
                "centered_syy": float(row["centered_syy"] or 0.0),
                "centered_sxy": float(row["centered_sxy"] or 0.0),
            }
            for row in rows
        ]
        return {
            "experiment_id": experiment_id,
            "numerator_metric": numerator_metric,
            "denominator_metric": denominator_metric,
            "variations": variations,
        }
