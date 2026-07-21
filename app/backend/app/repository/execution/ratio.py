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
        sufficient statistics the delta method needs — ``n``, ``sum_x``, ``sum_x2``, ``sum_y``,
        ``sum_y2``, ``sum_xy`` — from which ``stats.ratio`` computes ``R̂`` and its delta-method
        variance in the service layer (no new statistics in SQL). Every exposed user is the analysis
        unit (Kohavi et al.); the holdout tail (``variation_index = -1``) is excluded.
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
                )
                SELECT
                    variation_index,
                    COUNT(*) AS n,
                    SUM(x) AS sum_x,
                    SUM(x * x) AS sum_x2,
                    SUM(y) AS sum_y,
                    SUM(y * y) AS sum_y2,
                    SUM(x * y) AS sum_xy
                FROM user_pairs
                GROUP BY variation_index
                ORDER BY variation_index
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
            }
            for row in rows
        ]
        return {
            "experiment_id": experiment_id,
            "numerator_metric": numerator_metric,
            "denominator_metric": denominator_metric,
            "variations": variations,
        }
