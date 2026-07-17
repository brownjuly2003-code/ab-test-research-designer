"""Optional retention purge for high-volume operational tables (audit F-12).

Deletes are keyed by ISO-8601 timestamps already stored on each row. ``before``
cutoffs are exclusive upper bounds (``created_at < before``). Webhook deliveries
only purge terminal rows so in-flight outbox work is never dropped.
"""

from __future__ import annotations

from typing import Any

from app.backend.app.repository._core import _BackendCore


class _RetentionMixin(_BackendCore):
    def purge_retention_data(
        self,
        *,
        exposures_before: str | None = None,
        conversions_before: str | None = None,
        audit_before: str | None = None,
        webhook_deliveries_before: str | None = None,
        dry_run: bool = True,
    ) -> dict[str, int]:
        """Delete (or count) rows older than the given ISO cutoffs.

        Returns a map of table → affected row count. Empty cutoffs are no-ops.
        """
        counts: dict[str, int] = {
            "exposures": 0,
            "conversions": 0,
            "audit_log": 0,
            "webhook_deliveries": 0,
        }

        with self._connect() as connection:
            if exposures_before:
                counts["exposures"] = self._purge_table(
                    connection,
                    table="exposures",
                    timestamp_column="created_at",
                    before=exposures_before,
                    dry_run=dry_run,
                )
            if conversions_before:
                counts["conversions"] = self._purge_table(
                    connection,
                    table="conversions",
                    timestamp_column="created_at",
                    before=conversions_before,
                    dry_run=dry_run,
                )
            if audit_before:
                counts["audit_log"] = self._purge_table(
                    connection,
                    table="audit_log",
                    timestamp_column="ts",
                    before=audit_before,
                    dry_run=dry_run,
                )
            if webhook_deliveries_before:
                counts["webhook_deliveries"] = self._purge_webhook_deliveries(
                    connection,
                    before=webhook_deliveries_before,
                    dry_run=dry_run,
                )
            if not dry_run and any(counts.values()):
                connection.commit()

        return counts

    def _purge_table(
        self,
        connection: Any,
        *,
        table: str,
        timestamp_column: str,
        before: str,
        dry_run: bool,
    ) -> int:
        if dry_run:
            row = connection.execute(
                f"SELECT COUNT(*) AS n FROM {table} WHERE {timestamp_column} < ?",
                (before,),
            ).fetchone()
            return int(row["n"] if row is not None and "n" in row.keys() else row[0])

        cursor = connection.execute(
            f"DELETE FROM {table} WHERE {timestamp_column} < ?",
            (before,),
        )
        return int(cursor.rowcount or 0)

    def _purge_webhook_deliveries(
        self,
        connection: Any,
        *,
        before: str,
        dry_run: bool,
    ) -> int:
        # Only terminal rows — pending/retrying stay until the outbox finishes them.
        where = "created_at < ? AND status IN ('delivered', 'failed')"
        if dry_run:
            row = connection.execute(
                f"SELECT COUNT(*) AS n FROM webhook_deliveries WHERE {where}",
                (before,),
            ).fetchone()
            return int(row["n"] if row is not None and "n" in row.keys() else row[0])

        cursor = connection.execute(
            f"DELETE FROM webhook_deliveries WHERE {where}",
            (before,),
        )
        return int(cursor.rowcount or 0)
