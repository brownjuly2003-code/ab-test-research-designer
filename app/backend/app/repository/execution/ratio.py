"""Ratio-metric sufficient statistics over exposed users."""
from __future__ import annotations

from typing import Any

from app.backend.app.repository._core import _BackendCore
from app.backend.app.repository.execution.population import (
    ANALYTICAL_POPULATION_POLICY_VERSION,
    ratio_aggregate_sql,
    ratio_query_params,
)


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
        so modest scatter at large means is not lost to cancellation. Population semantics use the
        shared ``analytical_population_v1`` identity fold, first-exposure-wins arm and manual /
        rate-spike exclusions. Every in-population exposed user is the analysis unit (Kohavi et
        al.); the holdout tail is excluded by the treated-arm predicate.
        """
        with self._transaction() as connection:
            if not self._project_exists(connection, experiment_id):
                return None
            rows = connection.execute(
                ratio_aggregate_sql(),
                ratio_query_params(experiment_id, numerator_metric, denominator_metric),
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
            "population_policy_version": ANALYTICAL_POPULATION_POLICY_VERSION,
        }
