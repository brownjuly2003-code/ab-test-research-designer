"""Primary per-arm analysis aggregates over exposures/conversions."""
from __future__ import annotations

from typing import Any

from app.backend.app.repository._core import _BackendCore
from app.backend.app.repository.execution.population import (
    ANALYTICAL_POPULATION_POLICY_VERSION,
    aggregate_query_params,
    primary_aggregate_sql,
)


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

        Population semantics are the shared ``analytical_population_v1`` contract (identity
        one-hop fold, first-exposure-wins, manual + rate-spike exclusions). See
        ``repository.execution.population``.
        """
        with self._transaction() as connection:
            if not self._project_exists(connection, experiment_id):
                return None
            rows = connection.execute(
                primary_aggregate_sql(),
                aggregate_query_params(experiment_id, metric_name),
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
            "population_policy_version": ANALYTICAL_POPULATION_POLICY_VERSION,
        }
