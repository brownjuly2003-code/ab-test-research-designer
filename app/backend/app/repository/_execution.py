"""Execution layer: exposure/conversion ingestion and the aggregate read models."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.backend.app.constants import (
    BOT_CONVERSION_EVENT_THRESHOLD,
    HOLDOUT_VARIATION_INDEX,
    MAX_CUPED_COVARIATES,
    MAX_STRATA,
)
from app.backend.app.repository._core import _BackendCore
from app.backend.app.repository._utils import _normalize_occurred_at, _parse_iso


class _ExecutionMixin(_BackendCore):
    def record_exposures(self, experiment_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Record exposure events with first-exposure-wins dedup.

        Exactly one exposure survives per (experiment, user) thanks to the UNIQUE
        constraint + ``ON CONFLICT DO NOTHING``; a later (or duplicate) exposure for the
        same user is dropped, so the variation a user first saw stays sticky. Duplicate
        exposures would otherwise inflate one arm's count and manufacture a false SRM.
        """
        timestamp = datetime.now(UTC).isoformat()
        recorded = 0
        with self._connect() as connection:
            self._ensure_project_active(connection, experiment_id)
            for item in items:
                cursor = connection.execute(
                    """
                    INSERT INTO exposures (id, experiment_id, user_id, variation_index, created_at, occurred_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(experiment_id, user_id) DO NOTHING
                    """,
                    (
                        str(uuid.uuid4()),
                        experiment_id,
                        item["user_id"],
                        int(item["variation_index"]),
                        timestamp,
                        _normalize_occurred_at(item.get("occurred_at"), timestamp),
                    ),
                )
                if cursor.rowcount == 1:
                    recorded += 1
        received = len(items)
        return {"received": received, "recorded": recorded, "deduplicated": received - recorded}

    def record_conversions(self, experiment_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Record conversion events. When an ``idempotency_key`` is supplied, retries with
        the same key are deduped per experiment; events without a key are always recorded
        (NULLs are distinct in the UNIQUE index on both SQLite and Postgres)."""
        timestamp = datetime.now(UTC).isoformat()
        recorded = 0
        with self._connect() as connection:
            self._ensure_project_active(connection, experiment_id)
            for item in items:
                cursor = connection.execute(
                    """
                    INSERT INTO conversions (id, experiment_id, user_id, metric, value, idempotency_key, created_at, occurred_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(experiment_id, idempotency_key) DO NOTHING
                    """,
                    (
                        str(uuid.uuid4()),
                        experiment_id,
                        item["user_id"],
                        item["metric"],
                        float(item.get("value", 1.0)),
                        item.get("idempotency_key"),
                        timestamp,
                        _normalize_occurred_at(item.get("occurred_at"), timestamp),
                    ),
                )
                if cursor.rowcount == 1:
                    recorded += 1
        received = len(items)
        return {"received": received, "recorded": recorded, "deduplicated": received - recorded}

    def record_pre_period_values(self, experiment_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Record per-user pre-experiment covariate values for CUPED (E5 / F3a).

        First-write-wins per (experiment, user, covariate) via the UNIQUE constraint +
        ``ON CONFLICT DO NOTHING``; CUPED needs exactly one X per user per covariate, and the
        covariate is historical (pre-assignment) data, so a later value for the same key is dropped.
        Each item may carry a ``covariate_name``; single-covariate ingestion omits it and lands
        under the reserved ``__default__`` name, so the legacy one-covariate path is unchanged.
        """
        timestamp = datetime.now(UTC).isoformat()
        recorded = 0
        with self._connect() as connection:
            self._ensure_project_active(connection, experiment_id)
            for item in items:
                cursor = connection.execute(
                    """
                    INSERT INTO pre_period_covariates
                        (id, experiment_id, user_id, covariate_name, value, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(experiment_id, user_id, covariate_name) DO NOTHING
                    """,
                    (
                        str(uuid.uuid4()),
                        experiment_id,
                        item["user_id"],
                        item.get("covariate_name") or "__default__",
                        float(item["value"]),
                        timestamp,
                    ),
                )
                if cursor.rowcount == 1:
                    recorded += 1
        received = len(items)
        return {"received": received, "recorded": recorded, "deduplicated": received - recorded}

    def record_strata(self, experiment_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Record one categorical stratum per user for post-stratification (F3b).

        First-write-wins per (experiment, user) via the UNIQUE constraint + ``ON CONFLICT DO
        NOTHING``: the stratum is an assignment-time attribute (platform / country / new-vs-returning),
        so a later value for the same user is dropped, mirroring the first-exposure-wins exposure store.
        """
        timestamp = datetime.now(UTC).isoformat()
        recorded = 0
        with self._connect() as connection:
            self._ensure_project_active(connection, experiment_id)
            for item in items:
                cursor = connection.execute(
                    """
                    INSERT INTO user_strata (id, experiment_id, user_id, stratum, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(experiment_id, user_id) DO NOTHING
                    """,
                    (
                        str(uuid.uuid4()),
                        experiment_id,
                        item["user_id"],
                        str(item["stratum"]),
                        timestamp,
                    ),
                )
                if cursor.rowcount == 1:
                    recorded += 1
        received = len(items)
        return {"received": received, "recorded": recorded, "deduplicated": received - recorded}

    def record_holdout(self, experiment_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Record holdout members — users held back from the rollout — as ``variation_index = -1``
        exposures (F5).

        First-write-wins per (experiment, user) via the UNIQUE constraint + ``ON CONFLICT DO
        NOTHING``: a user already exposed to an arm keeps that arm (you cannot be both treated and
        held back), and a duplicate holdout entry is dropped. The holdout tail is excluded from the
        per-arm primary rollup (``get_experiment_analysis_aggregates`` filters ``variation_index >=
        0``); ``get_holdout_aggregates`` reads it back for the cumulative treated-vs-holdout view.
        Holdout outcomes ride the ordinary conversion stream under the primary metric name.
        """
        timestamp = datetime.now(UTC).isoformat()
        recorded = 0
        with self._connect() as connection:
            self._ensure_project_active(connection, experiment_id)
            for item in items:
                cursor = connection.execute(
                    """
                    INSERT INTO exposures (id, experiment_id, user_id, variation_index, created_at, occurred_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(experiment_id, user_id) DO NOTHING
                    """,
                    (
                        str(uuid.uuid4()),
                        experiment_id,
                        item["user_id"],
                        HOLDOUT_VARIATION_INDEX,
                        timestamp,
                        timestamp,
                    ),
                )
                if cursor.rowcount == 1:
                    recorded += 1
        received = len(items)
        return {"received": received, "recorded": recorded, "deduplicated": received - recorded}

    def record_identities(self, experiment_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Record anonymous → canonical identity links for identity resolution (P4.3).

        First-write-wins per (experiment, anonymous_id) via the UNIQUE constraint + ``ON CONFLICT DO
        NOTHING``: an anonymous_id resolves to exactly one canonical id, so a later re-link for the
        same anonymous_id is dropped (a stable canonical mapping). A link whose ``anonymous_id`` equals
        its ``canonical_id`` is a no-op identity and is skipped (it would never change a rollup and
        would only inflate the "linked" count). The primary rollup left-joins this map and folds each
        user's exposures/conversions onto their canonical id, so the same person counted under both an
        anonymous and a logged-in id collapses to one unit (no SRM inflation, no double conversion).
        """
        timestamp = datetime.now(UTC).isoformat()
        recorded = 0
        skipped = 0
        with self._connect() as connection:
            self._ensure_project_active(connection, experiment_id)
            for item in items:
                anonymous_id = item["anonymous_id"]
                canonical_id = item["canonical_id"]
                if anonymous_id == canonical_id:
                    skipped += 1
                    continue
                cursor = connection.execute(
                    """
                    INSERT INTO identity_map (id, experiment_id, anonymous_id, canonical_id, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(experiment_id, anonymous_id) DO NOTHING
                    """,
                    (
                        str(uuid.uuid4()),
                        experiment_id,
                        anonymous_id,
                        canonical_id,
                        timestamp,
                    ),
                )
                if cursor.rowcount == 1:
                    recorded += 1
        received = len(items)
        return {"received": received, "recorded": recorded, "deduplicated": received - recorded - skipped}

    def record_exclusions(self, experiment_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Record manual deny-list exclusions for the bot / fraud filter (P4.4).

        First-write-wins per (experiment, user) via the UNIQUE constraint + ``ON CONFLICT DO NOTHING``:
        the first recorded reason for a user sticks, and a duplicate exclusion is dropped. Excluded
        users are removed from every aggregate by the rollup's left-anti-join (resolved to their
        canonical id, so excluding an anonymous id also excludes the person's logged-in events). The
        raw exposure / conversion rows are never deleted — exclusion is a read-time filter — so an
        exclusion can be audited and the underlying events stay intact.
        """
        timestamp = datetime.now(UTC).isoformat()
        recorded = 0
        with self._connect() as connection:
            self._ensure_project_active(connection, experiment_id)
            for item in items:
                cursor = connection.execute(
                    """
                    INSERT INTO excluded_users
                        (id, experiment_id, user_id, exclusion_reason, source, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(experiment_id, user_id) DO NOTHING
                    """,
                    (
                        str(uuid.uuid4()),
                        experiment_id,
                        item["user_id"],
                        str(item.get("exclusion_reason") or "manual"),
                        "manual",
                        timestamp,
                    ),
                )
                if cursor.rowcount == 1:
                    recorded += 1
        received = len(items)
        return {"received": received, "recorded": recorded, "deduplicated": received - recorded}

    def get_user_exposure(self, experiment_id: str, user_id: str) -> dict[str, Any] | None:
        """The recorded (first-exposure-wins) exposure for one user, or ``None``.

        This is the sticky-bucket store: once a user has been exposed, the assignment
        endpoint reuses the stored ``variation_index`` so the user keeps their variation
        even if the experiment's weights or coverage change mid-flight.
        """
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT variation_index, created_at
                FROM exposures
                WHERE experiment_id = ? AND user_id = ?
                """,
                (experiment_id, user_id),
            ).fetchone()
        if row is None:
            return None
        return {"variation_index": int(row["variation_index"]), "created_at": row["created_at"]}

    def get_ingestion_summary(self, experiment_id: str) -> dict[str, Any] | None:
        """Per-variation exposure counts and per-metric conversion counts for an
        experiment. Returns ``None`` if the experiment does not exist. This is the raw
        aggregate Phase D's live SRM / sequential / Bayesian reads will build on."""
        with self._connect() as connection:
            if not self._project_exists(connection, experiment_id):
                return None
            exposure_rows = connection.execute(
                """
                SELECT variation_index, COUNT(*) AS count
                FROM exposures
                WHERE experiment_id = ?
                GROUP BY variation_index
                ORDER BY variation_index
                """,
                (experiment_id,),
            ).fetchall()
            conversion_rows = connection.execute(
                """
                SELECT metric, COUNT(*) AS count, COALESCE(SUM(value), 0) AS value_sum
                FROM conversions
                WHERE experiment_id = ?
                GROUP BY metric
                ORDER BY metric
                """,
                (experiment_id,),
            ).fetchall()
        exposure_counts = [
            {"variation_index": int(row["variation_index"]), "count": int(row["count"])}
            for row in exposure_rows
        ]
        conversion_counts = [
            {"metric": row["metric"], "count": int(row["count"]), "value_sum": float(row["value_sum"])}
            for row in conversion_rows
        ]
        return {
            "experiment_id": experiment_id,
            "exposures_total": sum(item["count"] for item in exposure_counts),
            "exposure_counts": exposure_counts,
            "conversions_total": sum(item["count"] for item in conversion_counts),
            "conversion_counts": conversion_counts,
        }

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
        with self._connect() as connection:
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
        with self._connect() as connection:
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
        with self._connect() as connection:
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
        with self._connect() as connection:
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
        with self._connect() as connection:
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
        with self._connect() as connection:
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
