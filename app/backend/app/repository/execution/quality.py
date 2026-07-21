"""Identity resolution, exclusions, holdout, and event-timing rollups."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.backend.app.constants import (
    BOT_CONVERSION_EVENT_THRESHOLD,
)
from app.backend.app.repository._core import _BackendCore
from app.backend.app.repository._utils import _parse_iso


class _QualityRollupMixin(_BackendCore):
    def get_identity_resolution_summary(self, experiment_id: str) -> dict[str, Any] | None:
        """Informational identity-resolution counts for the live-stats indicator (P4.3).

        Returns ``None`` if the experiment does not exist. Reports:

        - ``linked_identities``     — anonymous → canonical links recorded for the experiment.
        - ``canonicalized_events``  — exposure + conversion events whose ``user_id`` is a linked
          anonymous id, i.e. events the rollup re-attributes to a canonical id.
        - ``merged_users``          — distinct canonical ids that actually absorbed events from a
          linked anonymous id (the people whose double-count was prevented).

        Purely diagnostic — it does not change any rollup or verdict. All three are zero when no
        identity links exist, so the indicator is hidden in the common case.
        """
        with self._transaction() as connection:
            if not self._project_exists(connection, experiment_id):
                return None
            linked = connection.execute(
                "SELECT COUNT(*) AS n FROM identity_map WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()["n"]
            canon_exposures = connection.execute(
                """
                SELECT COUNT(*) AS n
                FROM exposures e
                JOIN identity_map im
                    ON im.experiment_id = e.experiment_id AND im.anonymous_id = e.user_id
                WHERE e.experiment_id = ?
                """,
                (experiment_id,),
            ).fetchone()["n"]
            canon_conversions = connection.execute(
                """
                SELECT COUNT(*) AS n
                FROM conversions c
                JOIN identity_map im
                    ON im.experiment_id = c.experiment_id AND im.anonymous_id = c.user_id
                WHERE c.experiment_id = ?
                """,
                (experiment_id,),
            ).fetchone()["n"]
            merged = connection.execute(
                """
                SELECT COUNT(DISTINCT im.canonical_id) AS n
                FROM identity_map im
                WHERE im.experiment_id = ?
                    AND (
                        EXISTS (
                            SELECT 1 FROM exposures e
                            WHERE e.experiment_id = im.experiment_id AND e.user_id = im.anonymous_id
                        )
                        OR EXISTS (
                            SELECT 1 FROM conversions c
                            WHERE c.experiment_id = im.experiment_id AND c.user_id = im.anonymous_id
                        )
                    )
                """,
                (experiment_id,),
            ).fetchone()["n"]
        return {
            "experiment_id": experiment_id,
            "linked_identities": int(linked or 0),
            "canonicalized_events": int((canon_exposures or 0) + (canon_conversions or 0)),
            "merged_users": int(merged or 0),
        }

    def get_exclusion_summary(self, experiment_id: str, _metric_name: str) -> dict[str, Any] | None:
        """Bot / fraud filter counts for the live-stats indicator (P4.4).

        Returns ``None`` if the experiment does not exist. Counts the *exposed* canonical users the
        rollup removes, split by reason (disjoint, manual takes precedence):

        - ``manual_filtered``     — exposed users on the manual deny-list (resolved to canonical).
        - ``rate_spike_filtered`` — exposed users over ``BOT_CONVERSION_EVENT_THRESHOLD`` conversion
          events across *all* of the experiment's metrics (not scoped to one metric — see
          ``get_experiment_analysis_aggregates``) and not already on the deny-list.
        - ``total_filtered``      — their sum (distinct exposed users removed).

        ``_metric_name`` is unused now that rate-spike is experiment-global; kept so the call site
        (one summary per live-stats read, alongside the per-metric rollups) doesn't need to change.

        Counts only exposed users (the population the rollup analyzes), so a deny-list entry for a user
        who was never exposed does not inflate the indicator. All zero when nothing is filtered, so the
        block is hidden in the common case. Purely informational — the exclusion already happened in
        the rollup; this reports it.
        """
        with self._transaction() as connection:
            if not self._project_exists(connection, experiment_id):
                return None
            row = connection.execute(
                """
                WITH exp_resolved AS (
                    SELECT DISTINCT COALESCE(im.canonical_id, e.user_id) AS cuser
                    FROM exposures e
                    LEFT JOIN identity_map im
                        ON im.experiment_id = e.experiment_id AND im.anonymous_id = e.user_id
                    WHERE e.experiment_id = ? AND e.variation_index >= 0
                ),
                conv_resolved AS (
                    -- Every metric, not just ``metric_name`` — a bot is a property of the user, so
                    -- the same set of rate-spike users must be reported regardless of which metric's
                    -- indicator is being read (mirrors ``get_experiment_analysis_aggregates``).
                    SELECT COALESCE(im.canonical_id, c.user_id) AS cuser
                    FROM conversions c
                    LEFT JOIN identity_map im
                        ON im.experiment_id = c.experiment_id AND im.anonymous_id = c.user_id
                    WHERE c.experiment_id = ?
                ),
                spike AS (
                    SELECT cuser FROM conv_resolved GROUP BY cuser HAVING COUNT(*) > ?
                ),
                manual AS (
                    SELECT DISTINCT COALESCE(im.canonical_id, x.user_id) AS cuser
                    FROM excluded_users x
                    LEFT JOIN identity_map im
                        ON im.experiment_id = x.experiment_id AND im.anonymous_id = x.user_id
                    WHERE x.experiment_id = ?
                ),
                flagged AS (
                    SELECT
                        CASE WHEN EXISTS (SELECT 1 FROM manual m WHERE m.cuser = er.cuser)
                             THEN 1 ELSE 0 END AS is_manual,
                        CASE WHEN EXISTS (SELECT 1 FROM spike sp WHERE sp.cuser = er.cuser)
                             THEN 1 ELSE 0 END AS is_spike
                    FROM exp_resolved er
                )
                SELECT
                    COALESCE(SUM(CASE WHEN is_manual = 1 OR is_spike = 1 THEN 1 ELSE 0 END), 0) AS total_filtered,
                    COALESCE(SUM(is_manual), 0) AS manual_filtered,
                    COALESCE(SUM(CASE WHEN is_spike = 1 AND is_manual = 0 THEN 1 ELSE 0 END), 0) AS rate_spike_filtered
                FROM flagged
                """,
                (
                    experiment_id,
                    experiment_id,
                    BOT_CONVERSION_EVENT_THRESHOLD,
                    experiment_id,
                ),
            ).fetchone()
        return {
            "experiment_id": experiment_id,
            "total_filtered": int(row["total_filtered"] or 0),
            "manual_filtered": int(row["manual_filtered"] or 0),
            "rate_spike_filtered": int(row["rate_spike_filtered"] or 0),
        }

    def get_holdout_aggregates(
        self, experiment_id: str, metric_name: str
    ) -> dict[str, Any] | None:
        """Held-back (``variation_index = -1``) rollup for the cumulative holdout read (F5).

        Returns ``None`` if the experiment does not exist. Mirrors
        ``get_experiment_analysis_aggregates`` but selects the holdout tail the per-arm rollup
        *excludes* — ``WHERE variation_index = -1`` — and folds it into a single ``holdout`` group
        with the same shape (``exposed_users``, ``converted_users``, ``value_sum``, ``value_sq_sum``).
        A user with several conversion events still counts once for the binary rate and contributes
        the sum of their values to the continuous rollup. The pooled treated arms come from the main
        aggregates (``variation_index >= 1``), so no second treated query is needed here.
        """
        with self._transaction() as connection:
            if not self._project_exists(connection, experiment_id):
                return None
            row = connection.execute(
                """
                WITH user_values AS (
                    SELECT
                        e.user_id AS user_id,
                        COALESCE(SUM(c.value), 0) AS user_value,
                        MAX(CASE WHEN c.id IS NOT NULL THEN 1 ELSE 0 END) AS converted
                    FROM exposures e
                    LEFT JOIN conversions c
                        ON c.experiment_id = e.experiment_id
                        AND c.user_id = e.user_id
                        AND c.metric = ?
                    WHERE e.experiment_id = ? AND e.variation_index = -1
                    GROUP BY e.user_id
                )
                SELECT
                    COUNT(*) AS exposed_users,
                    SUM(converted) AS converted_users,
                    SUM(user_value) AS value_sum,
                    SUM(user_value * user_value) AS value_sq_sum
                FROM user_values
                """,
                (metric_name, experiment_id),
            ).fetchone()
        holdout = {
            "exposed_users": int(row["exposed_users"] or 0) if row is not None else 0,
            "converted_users": int(row["converted_users"] or 0) if row is not None else 0,
            "value_sum": float(row["value_sum"] or 0.0) if row is not None else 0.0,
            "value_sq_sum": float(row["value_sq_sum"] or 0.0) if row is not None else 0.0,
        }
        return {
            "experiment_id": experiment_id,
            "metric_name": metric_name,
            "holdout": holdout,
        }

    def get_event_timing_summary(
        self, experiment_id: str, metric_name: str, horizon_days: float
    ) -> dict[str, Any] | None:
        """Classify each conversion on ``metric_name`` by its event time relative to the converting
        user's exposure (P4.2 late / out-of-order detection — the first consumer of P4.1 occurred_at).

        Returns ``None`` if the experiment does not exist. For every (exposed user with
        ``variation_index >= 0``, conversion on the metric) pair it compares the conversion's
        ``occurred_at`` (client event time) to that user's exposure ``occurred_at``:

        - ``out_of_order`` — conversion strictly before the exposure (causally impossible; a clock-skew
          or ingest-order artifact).
        - ``late`` — conversion more than ``horizon_days`` after the exposure (outside the attribution
          window).
        - ``in_window`` — within ``[exposure, exposure + horizon_days]``.

        Counts are over conversion *events* (a user with several conversions contributes each). The
        holdout tail (``variation_index = -1``) is excluded. This is an informational diagnostic — it
        does not change the primary rollup (``get_experiment_analysis_aggregates`` stays event-time
        agnostic) or any verdict. The ISO-8601 strings are parsed and compared in Python so the two
        backends share one portable query (no SQLite ``julianday`` vs Postgres interval divergence).
        """
        with self._transaction() as connection:
            if not self._project_exists(connection, experiment_id):
                return None
            rows = connection.execute(
                """
                SELECT e.occurred_at AS exposure_at, c.occurred_at AS conversion_at
                FROM exposures e
                JOIN conversions c
                    ON c.experiment_id = e.experiment_id
                    AND c.user_id = e.user_id
                    AND c.metric = ?
                WHERE e.experiment_id = ? AND e.variation_index >= 0
                """,
                (metric_name, experiment_id),
            ).fetchall()
        horizon = timedelta(days=horizon_days)
        in_window = 0
        late = 0
        out_of_order = 0
        for row in rows:
            exposure_at = _parse_iso(row["exposure_at"])
            conversion_at = _parse_iso(row["conversion_at"])
            if exposure_at is None or conversion_at is None:
                # Unparseable timestamps should not occur post-P4.1; count as neutral (in-window)
                # rather than flag a spurious anomaly.
                in_window += 1
            elif conversion_at < exposure_at:
                out_of_order += 1
            elif conversion_at > exposure_at + horizon:
                late += 1
            else:
                in_window += 1
        return {
            "experiment_id": experiment_id,
            "metric_name": metric_name,
            "horizon_days": horizon_days,
            "in_window": in_window,
            "late": late,
            "out_of_order": out_of_order,
            "total": in_window + late + out_of_order,
        }
