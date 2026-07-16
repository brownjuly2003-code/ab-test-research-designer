"""Exposure/conversion/identity/strata ingestion and summary counts."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.backend.app.constants import (
    HOLDOUT_VARIATION_INDEX,
)
from app.backend.app.repository._core import _BackendCore
from app.backend.app.repository._utils import _normalize_occurred_at


class _IngestionMixin(_BackendCore):
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
