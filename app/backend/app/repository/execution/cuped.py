"""Multi-covariate CUPED aggregate rollups."""
from __future__ import annotations

from typing import Any

from app.backend.app.constants import (
    MAX_CUPED_COVARIATES,
)
from app.backend.app.repository._core import _BackendCore


class _CupedRollupMixin(_BackendCore):
    def get_cuped_aggregates(self, experiment_id: str, metric_name: str) -> dict[str, Any] | None:
        """Per-variation multi-covariate CUPED sufficient statistics over the covered subset (F3a).

        Returns ``None`` if the experiment does not exist. The covariate names are discovered from
        the ingested ``pre_period_covariates`` rows (sorted; single-covariate CUPED is the special
        case of the lone ``__default__`` name). Restricted to exposed users that carry the
        **complete** covariate vector — CUPED can only adjust users whose every X is known — with
        the holdout tail (``variation_index = -1``) excluded. Per user the outcome ``Y`` is the sum
        of their conversion values on ``metric_name`` (non-converters contribute 0). Per variation it
        rolls up the regression sufficient statistics — ``n``, ``sum_y``, ``sum_y2`` and, over the
        covariate vector, ``sum_x[]``, ``sum_xy[]`` and the symmetric raw cross-moment matrix
        ``sum_xx[][]`` — from which the service forms the pooled coefficient vector
        ``theta = Sigma_xx^{-1} Sigma_xy`` and the per-arm adjusted moments (no new statistics in
        SQL). The k×k matrix is assembled in Python so the SQL stays covariate-count-agnostic and
        portable across SQLite and Postgres. ``too_many_covariates`` flags the pathological case of
        more than ``MAX_CUPED_COVARIATES`` distinct names (the heavy rollup is then skipped).
        """
        with self._connect() as connection:
            if not self._project_exists(connection, experiment_id):
                return None
            name_rows = connection.execute(
                """
                SELECT DISTINCT covariate_name
                FROM pre_period_covariates
                WHERE experiment_id = ?
                ORDER BY covariate_name
                """,
                (experiment_id,),
            ).fetchall()
            covariate_names = [str(row["covariate_name"]) for row in name_rows]
            if not covariate_names:
                return self._empty_cuped_aggregates(experiment_id, metric_name)
            if len(covariate_names) > MAX_CUPED_COVARIATES:
                result = self._empty_cuped_aggregates(experiment_id, metric_name)
                result["covariate_names"] = covariate_names
                result["too_many_covariates"] = True
                return result

            count = len(covariate_names)
            index_of = {name: position for position, name in enumerate(covariate_names)}

            # Shared CTEs: exposed-user outcomes Y, the experiment's covariate rows, and the
            # "covered" users that carry the complete covariate vector (all ``count`` covariates).
            covered_cte = """
                WITH user_outcomes AS (
                    SELECT
                        e.variation_index AS variation_index,
                        e.user_id AS user_id,
                        COALESCE(SUM(c.value), 0) AS y
                    FROM exposures e
                    LEFT JOIN conversions c
                        ON c.experiment_id = e.experiment_id
                        AND c.user_id = e.user_id
                        AND c.metric = ?
                    WHERE e.experiment_id = ? AND e.variation_index >= 0
                    GROUP BY e.variation_index, e.user_id
                ),
                user_cov AS (
                    SELECT user_id, covariate_name, value
                    FROM pre_period_covariates
                    WHERE experiment_id = ?
                ),
                covered AS (
                    SELECT o.variation_index AS variation_index, o.user_id AS user_id, o.y AS y
                    FROM user_outcomes o
                    JOIN user_cov uc ON uc.user_id = o.user_id
                    GROUP BY o.variation_index, o.user_id, o.y
                    HAVING COUNT(DISTINCT uc.covariate_name) = ?
                )
            """
            covered_params = (metric_name, experiment_id, experiment_id, count)

            variation_rows = connection.execute(
                covered_cte
                + """
                SELECT variation_index, COUNT(*) AS n, SUM(y) AS sum_y, SUM(y * y) AS sum_y2
                FROM covered
                GROUP BY variation_index
                ORDER BY variation_index
                """,
                covered_params,
            ).fetchall()

            covariate_rows = connection.execute(
                covered_cte
                + """
                SELECT
                    cv.variation_index AS variation_index,
                    uc.covariate_name AS covariate_name,
                    SUM(uc.value) AS sum_x,
                    SUM(uc.value * cv.y) AS sum_xy
                FROM covered cv
                JOIN user_cov uc ON uc.user_id = cv.user_id
                GROUP BY cv.variation_index, uc.covariate_name
                """,
                covered_params,
            ).fetchall()

            cross_rows = connection.execute(
                covered_cte
                + """
                SELECT
                    cv.variation_index AS variation_index,
                    a.covariate_name AS cov_i,
                    b.covariate_name AS cov_j,
                    SUM(a.value * b.value) AS sum_ij
                FROM covered cv
                JOIN user_cov a ON a.user_id = cv.user_id
                JOIN user_cov b ON b.user_id = cv.user_id AND a.covariate_name <= b.covariate_name
                GROUP BY cv.variation_index, a.covariate_name, b.covariate_name
                """,
                covered_params,
            ).fetchall()

        def blank(variation_index: int) -> dict[str, Any]:
            return {
                "variation_index": variation_index,
                "n": 0,
                "sum_y": 0.0,
                "sum_y2": 0.0,
                "sum_x": [0.0] * count,
                "sum_xy": [0.0] * count,
                "sum_xx": [[0.0] * count for _ in range(count)],
            }

        variations: dict[int, dict[str, Any]] = {}
        for row in variation_rows:
            index = int(row["variation_index"])
            entry = variations.setdefault(index, blank(index))
            entry["n"] = int(row["n"])
            entry["sum_y"] = float(row["sum_y"] or 0.0)
            entry["sum_y2"] = float(row["sum_y2"] or 0.0)
        for row in covariate_rows:
            index = int(row["variation_index"])
            name = str(row["covariate_name"])
            if name not in index_of:
                continue
            entry = variations.setdefault(index, blank(index))
            position = index_of[name]
            entry["sum_x"][position] = float(row["sum_x"] or 0.0)
            entry["sum_xy"][position] = float(row["sum_xy"] or 0.0)
        for row in cross_rows:
            index = int(row["variation_index"])
            name_i = str(row["cov_i"])
            name_j = str(row["cov_j"])
            if name_i not in index_of or name_j not in index_of:
                continue
            entry = variations.setdefault(index, blank(index))
            i = index_of[name_i]
            j = index_of[name_j]
            value = float(row["sum_ij"] or 0.0)
            entry["sum_xx"][i][j] = value
            entry["sum_xx"][j][i] = value

        ordered = [variations[index] for index in sorted(variations)]
        return {
            "experiment_id": experiment_id,
            "metric_name": metric_name,
            "covariate_names": covariate_names,
            "too_many_covariates": False,
            "variations": ordered,
        }

    @staticmethod
    def _empty_cuped_aggregates(experiment_id: str, metric_name: str) -> dict[str, Any]:
        return {
            "experiment_id": experiment_id,
            "metric_name": metric_name,
            "covariate_names": [],
            "too_many_covariates": False,
            "variations": [],
        }
