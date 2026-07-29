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
        **complete** covariate vector; users missing any X are excluded and the live response
        exposes coverage plus a selection caveat. The holdout tail (``variation_index = -1``) is
        excluded. Per user the outcome ``Y`` is the sum
        of their conversion values on ``metric_name`` (non-converters contribute 0). Per variation it
        rolls up the regression sufficient statistics — ``n``, ``sum_y``, ``sum_y2`` and, over the
        covariate vector, ``sum_x[]``, ``sum_xy[]`` and the symmetric raw cross-moment matrix
        ``sum_xx[][]`` — plus numerically stable within-arm centered SSCP computed by a portable
        two-pass mean/centered rollup: ``centered_syy``, ``centered_sxy[]``, ``centered_sxx[][]``.
        Raw keys are preserved for callers/tests; the service prefers the centered fields so modest
        within-arm signal at large means (e.g. ~1e9) is not lost to ``sum(v^2)-n*mean^2``
        catastrophic cancellation. One-ULP-negative variance/diagonal/Syy after centering are
        clamped to 0 in the service; positive centered signal and signed covariances are preserved
        (no relative-zero of small residuals).
        The k×k matrix is assembled in Python so the SQL stays covariate-count-agnostic and
        portable across SQLite and Postgres. ``too_many_covariates`` flags the pathological case of
        more than ``MAX_CUPED_COVARIATES`` distinct names (the heavy rollup is then skipped).
        """
        with self._transaction() as connection:
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

            # Shared CTEs: exposed-user outcomes Y, covariate rows, complete-vector "covered"
            # users, then per-arm / per-covariate means for a second-pass centered SSCP (avoids
            # catastrophic cancellation of raw second moments at large means).
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
                ),
                arm_means AS (
                    SELECT
                        variation_index,
                        SUM(y) * 1.0 / COUNT(*) AS mean_y
                    FROM covered
                    GROUP BY variation_index
                ),
                cov_means AS (
                    SELECT
                        cv.variation_index AS variation_index,
                        uc.covariate_name AS covariate_name,
                        SUM(uc.value) * 1.0 / COUNT(*) AS mean_x
                    FROM covered cv
                    JOIN user_cov uc ON uc.user_id = cv.user_id
                    GROUP BY cv.variation_index, uc.covariate_name
                )
            """
            covered_params = (metric_name, experiment_id, experiment_id, count)

            variation_rows = connection.execute(
                covered_cte
                + """
                SELECT
                    c.variation_index AS variation_index,
                    COUNT(*) AS n,
                    SUM(c.y) AS sum_y,
                    SUM(c.y * c.y) AS sum_y2,
                    SUM((c.y - m.mean_y) * (c.y - m.mean_y)) AS centered_syy
                FROM covered c
                JOIN arm_means m ON m.variation_index = c.variation_index
                GROUP BY c.variation_index
                ORDER BY c.variation_index
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
                    SUM(uc.value * cv.y) AS sum_xy,
                    SUM((uc.value - cm.mean_x) * (cv.y - am.mean_y)) AS centered_sxy
                FROM covered cv
                JOIN user_cov uc ON uc.user_id = cv.user_id
                JOIN arm_means am ON am.variation_index = cv.variation_index
                JOIN cov_means cm
                    ON cm.variation_index = cv.variation_index
                    AND cm.covariate_name = uc.covariate_name
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
                    SUM(a.value * b.value) AS sum_ij,
                    SUM((a.value - cma.mean_x) * (b.value - cmb.mean_x)) AS centered_sxx
                FROM covered cv
                JOIN user_cov a ON a.user_id = cv.user_id
                JOIN user_cov b ON b.user_id = cv.user_id AND a.covariate_name <= b.covariate_name
                JOIN cov_means cma
                    ON cma.variation_index = cv.variation_index
                    AND cma.covariate_name = a.covariate_name
                JOIN cov_means cmb
                    ON cmb.variation_index = cv.variation_index
                    AND cmb.covariate_name = b.covariate_name
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
                "centered_syy": 0.0,
                "centered_sxy": [0.0] * count,
                "centered_sxx": [[0.0] * count for _ in range(count)],
            }

        variations: dict[int, dict[str, Any]] = {}
        for row in variation_rows:
            index = int(row["variation_index"])
            entry = variations.setdefault(index, blank(index))
            entry["n"] = int(row["n"])
            entry["sum_y"] = float(row["sum_y"] or 0.0)
            entry["sum_y2"] = float(row["sum_y2"] or 0.0)
            entry["centered_syy"] = float(row["centered_syy"] or 0.0)
        for row in covariate_rows:
            index = int(row["variation_index"])
            name = str(row["covariate_name"])
            if name not in index_of:
                continue
            entry = variations.setdefault(index, blank(index))
            position = index_of[name]
            entry["sum_x"][position] = float(row["sum_x"] or 0.0)
            entry["sum_xy"][position] = float(row["sum_xy"] or 0.0)
            entry["centered_sxy"][position] = float(row["centered_sxy"] or 0.0)
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
            centered = float(row["centered_sxx"] or 0.0)
            entry["centered_sxx"][i][j] = centered
            entry["centered_sxx"][j][i] = centered

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
