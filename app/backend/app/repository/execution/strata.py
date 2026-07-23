"""Post-stratification aggregate rollups."""
from __future__ import annotations

from typing import Any

from app.backend.app.constants import (
    MAX_STRATA,
)
from app.backend.app.repository._core import _BackendCore
from app.backend.app.repository.execution.population import (
    ANALYTICAL_POPULATION_POLICY_VERSION,
    stratified_aggregate_sql,
    stratified_query_params,
)


class _StrataRollupMixin(_BackendCore):
    def get_stratified_aggregates(
        self, experiment_id: str, metric_name: str
    ) -> dict[str, Any] | None:
        """Per-(stratum, variation) analysis rollup for post-stratification (F3b).

        Returns ``None`` if the experiment does not exist. Uses the shared
        ``analytical_population_v1`` contract (identity fold, first-exposure-wins, manual +
        rate-spike exclusions), then inner-joins each resolved exposed user onto their recorded
        ``user_strata`` row (also identity-resolved) and groups by (stratum, variation). Users
        without a stratum are excluded; the holdout tail is excluded. ``too_many_strata`` flags
        more than ``MAX_STRATA`` distinct strata (rollup skipped).
        """
        with self._transaction() as connection:
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
                    "population_policy_version": ANALYTICAL_POPULATION_POLICY_VERSION,
                }
            rows = connection.execute(
                stratified_aggregate_sql(),
                stratified_query_params(experiment_id, metric_name),
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
            "population_policy_version": ANALYTICAL_POPULATION_POLICY_VERSION,
        }
