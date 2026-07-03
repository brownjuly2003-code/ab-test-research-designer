import csv
import hashlib
import hmac
import json
import secrets
import shutil
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, cast
from urllib.parse import unquote, urlparse

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from pydantic import ValidationError

from app.backend.app.constants import (
    BOT_CONVERSION_EVENT_THRESHOLD,
    HOLDOUT_VARIATION_INDEX,
    MAX_CUPED_COVARIATES,
    MAX_STRATA,
)
from app.backend.app.errors import ApiError
from app.backend.app.schemas.api import ExperimentInput


def _normalize_occurred_at(value: Any, fallback: str) -> str:
    """Normalize a client-supplied event time to a UTC ISO-8601 string (P4.1, event-time).

    ``occurred_at`` is when the event happened on the client; ``created_at`` (the ``fallback``)
    is when the server received it. ``value`` may be a ``datetime`` (parsed by the ingest schema),
    an ISO string, or ``None``. A naive datetime is assumed UTC; ``None`` or an unparseable value
    falls back to the server-receive time, so ``occurred_at`` defaults to the received time. This
    only records event-time; out-of-window / late attribution is layered on in P4.2.
    """
    if value is None:
        return fallback
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            return fallback
    else:
        return fallback
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat()


def _parse_iso(value: Any) -> datetime | None:
    """Parse a stored ISO-8601 timestamp back to a tz-aware datetime, or ``None`` if unparseable.

    Stored ``occurred_at`` / ``created_at`` values are UTC-aware ISO strings (see
    ``_normalize_occurred_at``); a naive value is treated as UTC so comparisons never mix
    naive/aware datetimes. Used by the P4.2 event-timing classification.
    """
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


class DatabaseBackend(Protocol):
    backend_name: str
    supports_snapshots: bool
    schema_version: int
    workspace_schema_version: int

    def set_webhook_service(self, webhook_service: Any | None) -> None: ...


class SQLiteBackend:
    backend_name = "sqlite"
    supports_snapshots = True
    schema_version = 14
    payload_schema_version = 1
    workspace_schema_version = 3
    project_select_columns = """
        projects.id,
        projects.project_name,
        projects.payload_json,
        projects.payload_schema_version,
        projects.archived_at,
        projects.last_analysis_at,
        projects.last_analysis_run_id,
        projects.last_exported_at,
        (
            SELECT COUNT(*)
            FROM project_revisions
            WHERE project_revisions.project_id = projects.id
        ) AS revision_count,
        (
            SELECT MAX(created_at)
            FROM project_revisions
            WHERE project_revisions.project_id = projects.id
        ) AS last_revision_at,
        projects.created_at,
        projects.updated_at
    """

    def __init__(
        self,
        db_path: str,
        *,
        busy_timeout_ms: int = 5000,
        journal_mode: str = "WAL",
        synchronous: str = "NORMAL",
        workspace_signing_key: str | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.busy_timeout_ms = int(busy_timeout_ms)
        self.journal_mode = journal_mode
        self.synchronous = synchronous
        self.workspace_signing_key = workspace_signing_key.strip() if workspace_signing_key else None
        self.webhook_service: Any | None = None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
        connection.execute(f"PRAGMA journal_mode = {self.journal_mode}")
        connection.execute(f"PRAGMA synchronous = {self.synchronous}")
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_schema_version INTEGER NOT NULL DEFAULT 1,
                    archived_at TEXT,
                    last_analysis_json TEXT,
                    last_analysis_at TEXT,
                    last_analysis_run_id TEXT,
                    last_exported_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._create_history_tables(connection)
            self._create_audit_tables(connection)
            self._create_api_key_tables(connection)
            self._create_webhook_tables(connection)
            self._create_slack_tables(connection)
            self._create_template_tables(connection)
            self._create_execution_tables(connection)
            self._migrate_db(connection)
            connection.execute(f"PRAGMA user_version = {self.schema_version}")

    @staticmethod
    def _decode_json_value(value: Any) -> Any:
        if value is None or isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            return json.loads(value)
        return value

    @staticmethod
    def _row_to_project(row: sqlite3.Row) -> dict[str, Any]:
        project = dict(row)
        payload_json = project.pop("payload_json")
        project["payload"] = SQLiteBackend._decode_json_value(payload_json)
        project["has_analysis_snapshot"] = bool(project.get("last_analysis_run_id"))
        project["is_archived"] = bool(project.get("archived_at"))
        return project

    @staticmethod
    def _create_history_tables(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                analysis_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_runs_project_created
            ON analysis_runs (project_id, created_at DESC)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS export_events (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                analysis_run_id TEXT,
                format TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(analysis_run_id) REFERENCES analysis_runs(id) ON DELETE SET NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_export_events_project_created
            ON export_events (project_id, created_at DESC)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS project_revisions (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_project_revisions_project_created
            ON project_revisions (project_id, created_at DESC)
            """
        )

    @staticmethod
    def _create_audit_tables(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                action TEXT NOT NULL,
                project_id TEXT,
                project_name TEXT,
                key_id TEXT,
                actor TEXT,
                request_id TEXT,
                payload_diff TEXT,
                ip_address TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_log_created
            ON audit_log (ts DESC, id DESC)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_log_project
            ON audit_log (project_id, ts DESC, id DESC)
            """
        )

    @staticmethod
    def _create_api_key_tables(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                key_hash TEXT NOT NULL UNIQUE,
                scope TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                revoked_at TEXT,
                rate_limit_requests INTEGER,
                rate_limit_window_seconds INTEGER
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_api_keys_scope_active
            ON api_keys (scope, revoked_at, created_at DESC)
            """
        )

    @staticmethod
    def _create_webhook_tables(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS webhook_subscriptions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                target_url TEXT NOT NULL,
                secret TEXT NOT NULL,
                format TEXT NOT NULL,
                event_filter TEXT NOT NULL DEFAULT '[]',
                scope TEXT NOT NULL,
                api_key_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_delivered_at TEXT,
                last_error_at TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY(api_key_id) REFERENCES api_keys(id) ON DELETE SET NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_webhook_subscriptions_scope_enabled
            ON webhook_subscriptions (scope, enabled, updated_at DESC)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS webhook_deliveries (
                id TEXT PRIMARY KEY,
                subscription_id TEXT NOT NULL,
                event_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_attempt_at TEXT,
                delivered_at TEXT,
                response_code INTEGER,
                response_body TEXT,
                error_message TEXT,
                FOREIGN KEY(subscription_id) REFERENCES webhook_subscriptions(id) ON DELETE CASCADE,
                FOREIGN KEY(event_id) REFERENCES audit_log(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_subscription_created
            ON webhook_deliveries (subscription_id, last_attempt_at DESC, id DESC)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_status
            ON webhook_deliveries (status, last_attempt_at DESC, id DESC)
            """
        )

    @staticmethod
    def _create_slack_tables(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS slack_installations (
                team_id TEXT PRIMARY KEY,
                team_name TEXT,
                bot_token TEXT NOT NULL,
                user_token TEXT,
                installed_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_slack_installations_updated
            ON slack_installations (updated_at DESC)
            """
        )

    @staticmethod
    def _create_template_tables(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS project_templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                built_in INTEGER NOT NULL DEFAULT 0,
                tags_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                usage_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_project_templates_updated
            ON project_templates (built_in DESC, updated_at DESC, id ASC)
            """
        )

    @staticmethod
    def _create_execution_tables(connection: sqlite3.Connection) -> None:
        # Execution layer (Phase C): raw exposure/conversion ingestion. The UNIQUE
        # constraints are the dedup primitives — exactly one exposure per (experiment,
        # user) gives first-exposure-wins (duplicate exposures directly produce a false
        # SRM otherwise), and an optional idempotency_key dedups conversion retries.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS exposures (
                id TEXT PRIMARY KEY,
                experiment_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                variation_index INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                UNIQUE(experiment_id, user_id),
                FOREIGN KEY(experiment_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_exposures_experiment_variation
            ON exposures (experiment_id, variation_index)
            """
        )
        # Event-time semantics (P4.1): occurred_at is the client event time (when it happened),
        # kept distinct from created_at (server-receive). On legacy rows it is backfilled to
        # created_at in _migrate_db; the late/out-of-order attribution that uses it arrives in P4.2.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversions (
                id TEXT PRIMARY KEY,
                experiment_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                metric TEXT NOT NULL,
                value REAL NOT NULL DEFAULT 1,
                idempotency_key TEXT,
                created_at TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                UNIQUE(experiment_id, idempotency_key),
                FOREIGN KEY(experiment_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_conversions_experiment_metric
            ON conversions (experiment_id, metric)
            """
        )
        # Per-user conversion lookup index (live-read performance). The heavy live-read rollups
        # (stratified / CUPED / ratio / event-timing / holdout) join each exposed user onto their
        # conversions with ``experiment_id = ? AND user_id = e.user_id AND metric = ?``; without a
        # composite index on (experiment_id, user_id, metric) that correlated join degrades to a
        # per-user scan. This index makes it a direct seek. Kept alongside the (experiment_id, metric)
        # index above, which still serves the metric-only filter in get_experiment_analysis_aggregates.
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_conversions_experiment_user_metric
            ON conversions (experiment_id, user_id, metric)
            """
        )
        # CUPED pre-period covariate (E5): one pre-experiment value per (experiment, user).
        # The UNIQUE constraint is the dedup primitive — first-write-wins keeps the covariate
        # stable. CUPED needs exactly one X per user paired with their outcome Y.
        # Retained for backward compatibility and as the migration source for the multi-covariate
        # table below; new writes go to pre_period_covariates (F3a).
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pre_period_values (
                id TEXT PRIMARY KEY,
                experiment_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                value REAL NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(experiment_id, user_id),
                FOREIGN KEY(experiment_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        # Multi-covariate CUPED (F3a): several named pre-experiment covariates per (experiment,
        # user). The named covariate is part of the dedup key so each (user, covariate) keeps one
        # first-write-wins value; single-covariate CUPED is the special case covariate_name =
        # '__default__'. Generalizes pre_period_values without a fragile UNIQUE-constraint rebuild.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pre_period_covariates (
                id TEXT PRIMARY KEY,
                experiment_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                covariate_name TEXT NOT NULL,
                value REAL NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(experiment_id, user_id, covariate_name),
                FOREIGN KEY(experiment_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        # Post-stratification (F3b): one categorical stratum per (experiment, user), known at
        # assignment time (platform / country / new-vs-returning). The UNIQUE constraint is the dedup
        # primitive — first-write-wins keeps the stratum stable, mirroring the exposure store. The
        # live-stats read joins this onto exposures to estimate the effect within each stratum and
        # recombine the per-stratum effects weighted by stratum size.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_strata (
                id TEXT PRIMARY KEY,
                experiment_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                stratum TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(experiment_id, user_id),
                FOREIGN KEY(experiment_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_user_strata_experiment_stratum
            ON user_strata (experiment_id, stratum)
            """
        )
        # Identity resolution (P4.3): maps an anonymous_id to the canonical (logged-in) id so a
        # person who is exposed while anonymous and converts (or is re-exposed) after login is counted
        # once, not twice. First-write-wins per (experiment, anonymous_id) via the UNIQUE constraint —
        # an anonymous_id resolves to exactly one canonical id, and a later re-link is dropped. The
        # primary rollup left-joins this map and folds each user's events onto their canonical id;
        # when the map is empty the rollup is byte-identical to the unresolved one.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS identity_map (
                id TEXT PRIMARY KEY,
                experiment_id TEXT NOT NULL,
                anonymous_id TEXT NOT NULL,
                canonical_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(experiment_id, anonymous_id),
                FOREIGN KEY(experiment_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_identity_map_experiment_anonymous
            ON identity_map (experiment_id, anonymous_id)
            """
        )
        # Bot / fraud filter (P4.4): a deny-list of users excluded from every aggregate. The
        # UNIQUE(experiment_id, user_id) constraint is the dedup primitive — first-write-wins keeps the
        # first recorded exclusion reason. ``source`` distinguishes a 'manual' deny-list entry from a
        # future automated writer; rate-spike exclusions are computed at read time (not stored) so the
        # raw events are never mutated. The rollup left-anti-joins this list (on the canonical id),
        # so when it is empty the rollup is unchanged.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS excluded_users (
                id TEXT PRIMARY KEY,
                experiment_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                exclusion_reason TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL,
                UNIQUE(experiment_id, user_id),
                FOREIGN KEY(experiment_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_excluded_users_experiment
            ON excluded_users (experiment_id, user_id)
            """
        )

    @staticmethod
    def _migrate_db(connection: sqlite3.Connection) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(projects)").fetchall()
        }
        required_columns = {
            "payload_schema_version": "INTEGER NOT NULL DEFAULT 1",
            "archived_at": "TEXT",
            "last_analysis_json": "TEXT",
            "last_analysis_at": "TEXT",
            "last_analysis_run_id": "TEXT",
            "last_exported_at": "TEXT",
        }

        for column_name, column_definition in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE projects ADD COLUMN {column_name} {column_definition}"
                )
        audit_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(audit_log)").fetchall()
        }
        if "key_id" not in audit_columns:
            connection.execute("ALTER TABLE audit_log ADD COLUMN key_id TEXT")
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_log_key
            ON audit_log (key_id, ts DESC, id DESC)
            """
        )
        # F3a: carry any legacy single-covariate pre-period values into the multi-covariate table
        # under the reserved '__default__' name. Idempotent (ON CONFLICT) — re-running on a
        # migrated DB copies nothing; a fresh DB has no legacy rows.
        connection.execute(
            """
            INSERT OR IGNORE INTO pre_period_covariates
                (id, experiment_id, user_id, covariate_name, value, created_at)
            SELECT lower(hex(randomblob(16))), experiment_id, user_id, '__default__', value, created_at
            FROM pre_period_values
            """
        )
        # Event-time backfill (P4.1): DBs created before occurred_at existed get the column added
        # (nullable — SQLite cannot retrofit a NOT NULL column) and backfilled to created_at, so
        # legacy events read occurred_at == server-receive time. New writes always populate it.
        for event_table in ("exposures", "conversions"):
            event_columns = {
                row["name"]
                for row in connection.execute(f"PRAGMA table_info({event_table})").fetchall()
            }
            if "occurred_at" not in event_columns:
                connection.execute(f"ALTER TABLE {event_table} ADD COLUMN occurred_at TEXT")
                connection.execute(
                    f"UPDATE {event_table} SET occurred_at = created_at WHERE occurred_at IS NULL"
                )

        def normalize_payload_json(payload_json: str) -> str | None:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                return None

            metrics = payload.get("metrics")
            if not isinstance(metrics, dict):
                return None

            guardrail_metrics = metrics.get("guardrail_metrics")
            if not isinstance(guardrail_metrics, list):
                return None

            normalized_guardrails = []
            changed = False
            for item in guardrail_metrics:
                if item == "payment_error_rate":
                    normalized_guardrails.append(
                        {
                            "name": "Payment error rate",
                            "metric_type": "binary",
                            "baseline_rate": 2.4,
                        }
                    )
                    changed = True
                else:
                    normalized_guardrails.append(item)

            if not changed:
                return None

            normalized_metrics = dict(metrics)
            normalized_metrics["guardrail_metrics"] = normalized_guardrails
            normalized_payload = dict(payload)
            normalized_payload["metrics"] = normalized_metrics
            return json.dumps(normalized_payload)

        SQLiteBackend._create_history_tables(connection)
        SQLiteBackend._create_audit_tables(connection)
        SQLiteBackend._create_api_key_tables(connection)
        SQLiteBackend._create_webhook_tables(connection)
        SQLiteBackend._create_slack_tables(connection)
        SQLiteBackend._create_template_tables(connection)
        for table_name in ("projects", "project_revisions"):
            rows = connection.execute(
                f"SELECT id, payload_json FROM {table_name}"
            ).fetchall()
            for row in rows:
                normalized_payload_json = normalize_payload_json(row["payload_json"])
                if normalized_payload_json is not None:
                    connection.execute(
                        f"UPDATE {table_name} SET payload_json = ? WHERE id = ?",
                        (normalized_payload_json, row["id"]),
                    )
        SQLiteBackend._backfill_analysis_runs(connection)
        SQLiteBackend._backfill_project_revisions(connection)

    @staticmethod
    def _flatten_payload(value: Any, *, prefix: str = "") -> dict[str, Any]:
        if isinstance(value, dict):
            flattened: dict[str, Any] = {}
            for key in sorted(value.keys()):
                child_prefix = f"{prefix}.{key}" if prefix else str(key)
                flattened.update(SQLiteBackend._flatten_payload(value[key], prefix=child_prefix))
            return flattened
        if isinstance(value, list):
            return {prefix: value}
        return {prefix: value}

    @staticmethod
    def build_payload_diff(previous_payload: dict[str, Any], next_payload: dict[str, Any]) -> dict[str, list[Any]]:
        previous = SQLiteBackend._flatten_payload(previous_payload)
        current = SQLiteBackend._flatten_payload(next_payload)
        changed_keys = sorted(set(previous.keys()) | set(current.keys()))
        diff: dict[str, list[Any]] = {}
        for key in changed_keys:
            if previous.get(key) != current.get(key):
                diff[key] = [previous.get(key), current.get(key)]
        return diff

    @staticmethod
    def _backfill_analysis_runs(connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT id, last_analysis_json, last_analysis_at, last_analysis_run_id
            FROM projects
            WHERE last_analysis_json IS NOT NULL AND last_analysis_json != ''
            """
        ).fetchall()

        for row in rows:
            existing_run = connection.execute(
                """
                SELECT id
                FROM analysis_runs
                WHERE project_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (row["id"],),
            ).fetchone()
            if existing_run is None:
                run_id = row["last_analysis_run_id"] or str(uuid.uuid4())
                created_at = row["last_analysis_at"] or datetime.now(UTC).isoformat()
                connection.execute(
                    """
                    INSERT INTO analysis_runs (id, project_id, analysis_json, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (run_id, row["id"], row["last_analysis_json"], created_at),
                )
                connection.execute(
                    "UPDATE projects SET last_analysis_run_id = ? WHERE id = ?",
                    (run_id, row["id"]),
                )
            elif row["last_analysis_run_id"] is None:
                connection.execute(
                    "UPDATE projects SET last_analysis_run_id = ? WHERE id = ?",
                    (existing_run["id"], row["id"]),
                )

    @staticmethod
    def _backfill_project_revisions(connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT id, payload_json, created_at
            FROM projects
            WHERE id NOT IN (
                SELECT project_id
                FROM project_revisions
            )
            """
        ).fetchall()

        for row in rows:
            connection.execute(
                """
                INSERT INTO project_revisions (id, project_id, payload_json, source, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    row["id"],
                    row["payload_json"],
                    "create",
                    row["created_at"],
                ),
            )

    @staticmethod
    def _build_analysis_summary(analysis_payload: dict[str, Any]) -> dict[str, Any]:
        calculations = analysis_payload.get("calculations", {})
        calculation_summary = calculations.get("calculation_summary", {})
        results = calculations.get("results", {})
        warnings = calculations.get("warnings", [])
        advice = analysis_payload.get("advice", {})

        return {
            "metric_type": calculation_summary.get("metric_type"),
            "sample_size_per_variant": results.get("sample_size_per_variant"),
            "total_sample_size": results.get("total_sample_size"),
            "estimated_duration_days": results.get("estimated_duration_days"),
            "warnings_count": len(warnings) if isinstance(warnings, list) else 0,
            "advice_available": bool(advice.get("available")),
        }

    @classmethod
    def _analysis_row_to_record(cls, row: sqlite3.Row) -> dict[str, Any]:
        analysis = cls._decode_json_value(row["analysis_json"])
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "created_at": row["created_at"],
            "summary": cls._build_analysis_summary(analysis),
            "analysis": analysis,
        }

    @staticmethod
    def _analysis_row_to_workspace_record(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "created_at": row["created_at"],
            "analysis": SQLiteBackend._decode_json_value(row["analysis_json"]),
        }

    @staticmethod
    def _export_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)

    @staticmethod
    def _revision_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "source": row["source"],
            "created_at": row["created_at"],
            "payload": SQLiteBackend._decode_json_value(row["payload_json"]),
        }

    @staticmethod
    def _api_key_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "scope": row["scope"],
            "created_at": row["created_at"],
            "last_used_at": row["last_used_at"],
            "revoked_at": row["revoked_at"],
            "rate_limit_requests": row["rate_limit_requests"],
            "rate_limit_window_seconds": row["rate_limit_window_seconds"],
        }

    @staticmethod
    def _webhook_subscription_row_to_record(
        row: sqlite3.Row,
        *,
        include_secret: bool = False,
    ) -> dict[str, Any]:
        event_filter_raw = row["event_filter"]
        return {
            "id": row["id"],
            "name": row["name"],
            "target_url": row["target_url"],
            "secret": row["secret"] if include_secret else None,
            "format": row["format"],
            "event_filter": SQLiteBackend._decode_json_value(event_filter_raw) if event_filter_raw else [],
            "scope": row["scope"],
            "api_key_id": row["api_key_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_delivered_at": row["last_delivered_at"],
            "last_error_at": row["last_error_at"],
            "enabled": bool(row["enabled"]),
        }

    @staticmethod
    def _webhook_delivery_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "subscription_id": row["subscription_id"],
            "event_id": row["event_id"],
            "status": row["status"],
            "attempt_count": int(row["attempt_count"]),
            "last_attempt_at": row["last_attempt_at"],
            "delivered_at": row["delivered_at"],
            "response_code": row["response_code"],
            "response_body": row["response_body"],
            "error_message": row["error_message"],
        }

    @staticmethod
    def _audit_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
        payload_diff_json = row["payload_diff"]
        return {
            "id": row["id"],
            "ts": row["ts"],
            "action": row["action"],
            "project_id": row["project_id"],
            "project_name": row["project_name"],
            "key_id": row["key_id"],
            "actor": row["actor"],
            "request_id": row["request_id"],
            "payload_diff": SQLiteBackend._decode_json_value(payload_diff_json) if payload_diff_json else None,
            "ip_address": row["ip_address"],
        }

    @staticmethod
    def build_api_key_hash(plaintext_key: str) -> str:
        return hashlib.sha256(plaintext_key.encode("utf-8")).hexdigest()

    def set_webhook_service(self, webhook_service: Any | None) -> None:
        self.webhook_service = webhook_service

    @classmethod
    def _project_row_to_workspace_record(cls, row: sqlite3.Row) -> dict[str, Any]:
        project = cls._row_to_project(row)
        project.pop("revision_count", None)
        project.pop("last_revision_at", None)
        project.pop("has_analysis_snapshot", None)
        project.pop("is_archived", None)
        return project

    @staticmethod
    def _project_list_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
        project = dict(row)
        project["has_analysis_snapshot"] = bool(project.get("has_analysis_snapshot"))
        project["is_archived"] = bool(project.get("is_archived"))
        return project

    @staticmethod
    def _create_revision(
        connection: sqlite3.Connection,
        project_id: str,
        payload: dict[str, Any],
        source: str,
        created_at: str,
        revision_id: str | None = None,
    ) -> str:
        resolved_revision_id = revision_id or str(uuid.uuid4())
        connection.execute(
            """
            INSERT INTO project_revisions (id, project_id, payload_json, source, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                resolved_revision_id,
                project_id,
                json.dumps(payload),
                source,
                created_at,
            ),
        )
        return resolved_revision_id

    def _get_project_row(
        self,
        connection: sqlite3.Connection,
        project_id: str,
        *,
        include_archived: bool = False,
    ) -> sqlite3.Row | None:
        archived_clause = "" if include_archived else "AND archived_at IS NULL"
        return cast(
            "sqlite3.Row | None",
            connection.execute(
                f"""
            SELECT {self.project_select_columns}
            FROM projects
            WHERE id = ? {archived_clause}
            """,
                (project_id,),
            ).fetchone(),
        )

    @staticmethod
    def _normalize_history_limit(limit: int) -> int:
        return max(1, min(int(limit), 100))

    @staticmethod
    def _normalize_history_offset(offset: int) -> int:
        return max(0, int(offset))

    def list_projects(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        archived_filter = "" if include_archived else "WHERE projects.archived_at IS NULL"
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    projects.id,
                    projects.project_name,
                    json_extract(projects.payload_json, '$.hypothesis.hypothesis_statement') AS hypothesis,
                    json_extract(projects.payload_json, '$.metrics.metric_type') AS metric_type,
                    CAST(
                        json_extract(
                            (
                                SELECT analysis_json
                                FROM analysis_runs
                                WHERE analysis_runs.project_id = projects.id
                                ORDER BY created_at DESC, id DESC
                                LIMIT 1
                            ),
                            '$.report.calculations.estimated_duration_days'
                        ) AS INTEGER
                    ) AS duration_days,
                    projects.payload_schema_version,
                    projects.archived_at,
                    (
                        SELECT COUNT(*)
                        FROM project_revisions
                        WHERE project_revisions.project_id = projects.id
                    ) AS revision_count,
                    (
                        SELECT MAX(created_at)
                        FROM project_revisions
                        WHERE project_revisions.project_id = projects.id
                    ) AS last_revision_at,
                    projects.last_analysis_at,
                    projects.last_analysis_run_id,
                    projects.last_exported_at,
                    CASE WHEN projects.last_analysis_run_id IS NOT NULL THEN 1 ELSE 0 END AS has_analysis_snapshot,
                    CASE WHEN projects.archived_at IS NOT NULL THEN 1 ELSE 0 END AS is_archived,
                    projects.created_at,
                    projects.updated_at
                FROM projects
                {archived_filter}
                ORDER BY projects.updated_at DESC
                """
            ).fetchall()
        return [self._project_list_row_to_record(row) for row in rows]

    def query_projects(
        self,
        *,
        q: str | None = None,
        status: str = "active",
        metric_type: str = "all",
        sort_by: str = "updated_at",
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        normalized_query = q.strip().lower() if isinstance(q, str) else ""
        normalized_status = status if status in {"active", "archived", "all"} else "active"
        normalized_metric_type = metric_type if metric_type in {"binary", "continuous", "ratio", "all"} else "all"
        normalized_sort_by = sort_by if sort_by in {"created_at", "updated_at", "name", "duration_days"} else "updated_at"
        normalized_sort_dir = "ASC" if str(sort_dir).lower() == "asc" else "DESC"
        where_clauses: list[str] = []
        params: list[object] = []

        if normalized_status == "active":
            where_clauses.append("projects.archived_at IS NULL")
        elif normalized_status == "archived":
            where_clauses.append("projects.archived_at IS NOT NULL")

        if normalized_metric_type != "all":
            where_clauses.append("json_extract(projects.payload_json, '$.metrics.metric_type') = ?")
            params.append(normalized_metric_type)

        if normalized_query:
            like_pattern = f"%{normalized_query}%"
            where_clauses.append(
                """
                (
                    lower(projects.project_name) LIKE ?
                    OR lower(COALESCE(json_extract(projects.payload_json, '$.hypothesis.hypothesis_statement'), '')) LIKE ?
                    OR lower(COALESCE(json_extract(projects.payload_json, '$.hypothesis.change_description'), '')) LIKE ?
                )
                """
            )
            params.extend([like_pattern, like_pattern, like_pattern])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        if normalized_sort_by == "name":
            order_sql = f"ORDER BY lower(projects.project_name) {normalized_sort_dir}, projects.updated_at DESC"
        elif normalized_sort_by == "duration_days":
            order_sql = f"ORDER BY duration_days IS NULL, duration_days {normalized_sort_dir}, projects.updated_at DESC"
        else:
            order_column = "projects.created_at" if normalized_sort_by == "created_at" else "projects.updated_at"
            order_sql = f"ORDER BY {order_column} {normalized_sort_dir}, projects.id DESC"

        with self._connect() as connection:
            total = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM projects
                {where_sql}
                """,
                params,
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT
                    projects.id,
                    projects.project_name,
                    json_extract(projects.payload_json, '$.hypothesis.hypothesis_statement') AS hypothesis,
                    json_extract(projects.payload_json, '$.metrics.metric_type') AS metric_type,
                    CAST(
                        json_extract(
                            (
                                SELECT analysis_json
                                FROM analysis_runs
                                WHERE analysis_runs.project_id = projects.id
                                ORDER BY created_at DESC, id DESC
                                LIMIT 1
                            ),
                            '$.report.calculations.estimated_duration_days'
                        ) AS INTEGER
                    ) AS duration_days,
                    projects.payload_schema_version,
                    projects.archived_at,
                    (
                        SELECT COUNT(*)
                        FROM project_revisions
                        WHERE project_revisions.project_id = projects.id
                    ) AS revision_count,
                    (
                        SELECT MAX(created_at)
                        FROM project_revisions
                        WHERE project_revisions.project_id = projects.id
                    ) AS last_revision_at,
                    projects.last_analysis_at,
                    projects.last_analysis_run_id,
                    projects.last_exported_at,
                    CASE WHEN projects.last_analysis_run_id IS NOT NULL THEN 1 ELSE 0 END AS has_analysis_snapshot,
                    CASE WHEN projects.archived_at IS NOT NULL THEN 1 ELSE 0 END AS is_archived,
                    projects.created_at,
                    projects.updated_at
                FROM projects
                {where_sql}
                {order_sql}
                LIMIT ?
                OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()

        return {
            "projects": [self._project_list_row_to_record(row) for row in rows],
            "total": int(total),
            "offset": offset,
            "limit": limit,
            "has_more": (offset + len(rows)) < int(total),
        }

    def create_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_id = str(uuid.uuid4())
        timestamp = datetime.now(UTC).isoformat()
        project_name = payload["project"]["project_name"]

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO projects (
                    id,
                    project_name,
                    payload_json,
                    payload_schema_version,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    project_name,
                    json.dumps(payload),
                    self.payload_schema_version,
                    timestamp,
                    timestamp,
                ),
            )
            self._create_revision(connection, project_id, payload, "create", timestamp)

        # The project was just inserted in this transaction, so it always exists.
        return cast("dict[str, Any]", self.get_project(project_id, include_archived=True))

    def get_project(self, project_id: str, *, include_archived: bool = False) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = self._get_project_row(connection, project_id, include_archived=include_archived)

        if row is None:
            return None

        return self._row_to_project(row)

    def _project_exists(self, connection: sqlite3.Connection, project_id: str) -> bool:
        row = connection.execute(
            "SELECT 1 FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        return row is not None

    def _ensure_project_active(self, connection: sqlite3.Connection, project_id: str) -> None:
        row = connection.execute(
            "SELECT archived_at FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            raise ApiError("Project not found", error_code="project_not_found", status_code=404)
        if row["archived_at"] is not None:
            raise ApiError("Project is archived", error_code="project_archived")

    def update_project(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        timestamp = datetime.now(UTC).isoformat()
        project_name = payload["project"]["project_name"]

        with self._connect() as connection:
            self._ensure_project_active(connection, project_id)
            cursor = connection.execute(
                """
                UPDATE projects
                SET project_name = ?, payload_json = ?, payload_schema_version = ?, updated_at = ?
                WHERE id = ? AND archived_at IS NULL
                """,
                (
                    project_name,
                    json.dumps(payload),
                    self.payload_schema_version,
                    timestamp,
                    project_id,
                ),
            )
            if cursor.rowcount > 0:
                self._create_revision(connection, project_id, payload, "update", timestamp)

        if cursor.rowcount == 0:
            return None

        return self.get_project(project_id, include_archived=True)

    def record_analysis(self, project_id: str, analysis_payload: dict[str, Any]) -> dict[str, Any] | None:
        timestamp = datetime.now(UTC).isoformat()
        analysis_run_id = str(uuid.uuid4())

        with self._connect() as connection:
            self._ensure_project_active(connection, project_id)

            connection.execute(
                """
                INSERT INTO analysis_runs (id, project_id, analysis_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (analysis_run_id, project_id, json.dumps(analysis_payload), timestamp),
            )
            cursor = connection.execute(
                """
                UPDATE projects
                SET last_analysis_at = ?, last_analysis_run_id = ?
                WHERE id = ? AND archived_at IS NULL
                """,
                (timestamp, analysis_run_id, project_id),
            )

        if cursor.rowcount == 0:
            return None

        return self.get_project(project_id, include_archived=True)

    def record_export(self, project_id: str, export_format: str, analysis_run_id: str | None = None) -> dict[str, Any] | None:
        timestamp = datetime.now(UTC).isoformat()
        export_event_id = str(uuid.uuid4())

        with self._connect() as connection:
            self._ensure_project_active(connection, project_id)

            if analysis_run_id is not None:
                linked_run = connection.execute(
                    """
                    SELECT 1
                    FROM analysis_runs
                    WHERE id = ? AND project_id = ?
                    """,
                    (analysis_run_id, project_id),
                ).fetchone()
                if linked_run is None:
                    raise ApiError(
                        "Analysis run not found for project",
                        error_code="analysis_run_not_found",
                    )

            connection.execute(
                """
                INSERT INTO export_events (id, project_id, analysis_run_id, format, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (export_event_id, project_id, analysis_run_id, export_format, timestamp),
            )
            cursor = connection.execute(
                """
                UPDATE projects
                SET last_exported_at = ?
                WHERE id = ? AND archived_at IS NULL
                """,
                (timestamp, project_id),
            )

        if cursor.rowcount == 0:
            return None

        return self.get_project(project_id, include_archived=True)

    def upsert_slack_installation(
        self,
        *,
        team_id: str,
        team_name: str | None,
        bot_token: str,
        user_token: str | None = None,
    ) -> dict[str, Any]:
        timestamp = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO slack_installations (
                    team_id,
                    team_name,
                    bot_token,
                    user_token,
                    installed_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(team_id) DO UPDATE SET
                    team_name = excluded.team_name,
                    bot_token = excluded.bot_token,
                    user_token = excluded.user_token,
                    updated_at = excluded.updated_at
                """,
                (team_id, team_name, bot_token, user_token, timestamp, timestamp),
            )
        installation = self.get_slack_installation(team_id)
        if installation is None:
            raise ApiError("Slack installation not found", error_code="slack_installation_not_found", status_code=500)
        return installation

    def get_slack_installation(self, team_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT team_id, team_name, bot_token, user_token, installed_at, updated_at
                FROM slack_installations
                WHERE team_id = ?
                """,
                (team_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def get_latest_slack_installation(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT team_id, team_name, bot_token, user_token, installed_at, updated_at
                FROM slack_installations
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ).fetchone()
        return dict(row) if row is not None else None

    @staticmethod
    def _template_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "description": row["description"],
            "built_in": bool(row["built_in"]),
            "tags": SQLiteBackend._decode_json_value(row["tags_json"]),
            "payload": SQLiteBackend._decode_json_value(row["payload_json"]),
            "usage_count": int(row["usage_count"]),
        }

    def upsert_template(
        self,
        *,
        template_id: str,
        name: str,
        category: str,
        description: str,
        built_in: bool,
        tags: list[str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        timestamp = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO project_templates (
                    id,
                    name,
                    category,
                    description,
                    built_in,
                    tags_json,
                    payload_json,
                    usage_count,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    category = excluded.category,
                    description = excluded.description,
                    built_in = excluded.built_in,
                    tags_json = excluded.tags_json,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    template_id,
                    name,
                    category,
                    description,
                    1 if built_in else 0,
                    json.dumps(tags),
                    json.dumps(payload),
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                """
                SELECT id, name, category, description, built_in, tags_json, payload_json, usage_count
                FROM project_templates
                WHERE id = ?
                """,
                (template_id,),
            ).fetchone()

        return self._template_row_to_record(row)

    def list_templates(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, category, description, built_in, tags_json, payload_json, usage_count
                FROM project_templates
                ORDER BY built_in DESC, usage_count DESC, name COLLATE NOCASE ASC
                """
            ).fetchall()
        return [self._template_row_to_record(row) for row in rows]

    def get_template(self, template_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, category, description, built_in, tags_json, payload_json, usage_count
                FROM project_templates
                WHERE id = ?
                """,
                (template_id,),
            ).fetchone()
        return self._template_row_to_record(row) if row is not None else None

    def create_template(
        self,
        *,
        name: str,
        category: str,
        description: str,
        tags: list[str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self.upsert_template(
            template_id=str(uuid.uuid4()),
            name=name,
            category=category,
            description=description,
            built_in=False,
            tags=tags,
            payload=payload,
        )

    def use_template(self, template_id: str) -> dict[str, Any] | None:
        timestamp = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE project_templates
                SET usage_count = usage_count + 1, updated_at = ?
                WHERE id = ?
                """,
                (timestamp, template_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT id, name, category, description, built_in, tags_json, payload_json, usage_count
                FROM project_templates
                WHERE id = ?
                """,
                (template_id,),
            ).fetchone()
        return self._template_row_to_record(row) if row is not None else None

    def delete_template(self, template_id: str) -> dict[str, Any] | None:
        existing = self.get_template(template_id)
        if existing is None:
            return None
        if existing["built_in"]:
            raise ApiError(
                "Built-in templates cannot be deleted",
                error_code="template_delete_forbidden",
                status_code=403,
            )
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM project_templates WHERE id = ?",
                (template_id,),
            )
        return {
            "id": template_id,
            "deleted": True,
        }

    def has_api_keys(self) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM api_keys
                LIMIT 1
                """
            ).fetchone()
        return row is not None

    def has_active_api_keys(self, *, scope: str | None = None) -> bool:
        scope_filters = {
            "write": ("write", "admin"),
            "read": ("read", "write", "admin"),
            "admin": ("admin",),
        }
        scopes = scope_filters.get(scope) if scope is not None else None
        with self._connect() as connection:
            if scopes is None:
                row = connection.execute(
                    """
                    SELECT 1
                    FROM api_keys
                    WHERE revoked_at IS NULL
                    LIMIT 1
                    """
                ).fetchone()
            else:
                placeholders = ", ".join("?" for _ in scopes)
                row = connection.execute(
                    f"""
                    SELECT 1
                    FROM api_keys
                    WHERE revoked_at IS NULL AND scope IN ({placeholders})
                    LIMIT 1
                    """,
                    scopes,
                ).fetchone()
        return row is not None

    def create_api_key(
        self,
        *,
        name: str,
        scope: str,
        rate_limit_requests: int | None = None,
        rate_limit_window_seconds: int | None = None,
    ) -> dict[str, Any]:
        api_key_id = str(uuid.uuid4())
        plaintext_key = f"abk_{secrets.token_urlsafe(32)}"
        key_hash = self.build_api_key_hash(plaintext_key)
        created_at = datetime.now(UTC).isoformat()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO api_keys (
                    id,
                    name,
                    key_hash,
                    scope,
                    created_at,
                    last_used_at,
                    revoked_at,
                    rate_limit_requests,
                    rate_limit_window_seconds
                )
                VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?)
                """,
                (
                    api_key_id,
                    name,
                    key_hash,
                    scope,
                    created_at,
                    rate_limit_requests,
                    rate_limit_window_seconds,
                ),
            )

        return {
            "id": api_key_id,
            "name": name,
            "scope": scope,
            "created_at": created_at,
            "last_used_at": None,
            "revoked_at": None,
            "rate_limit_requests": rate_limit_requests,
            "rate_limit_window_seconds": rate_limit_window_seconds,
            "plaintext_key": plaintext_key,
        }

    def list_api_keys(self) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    name,
                    scope,
                    created_at,
                    last_used_at,
                    revoked_at,
                    rate_limit_requests,
                    rate_limit_window_seconds
                FROM api_keys
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()

        keys = [self._api_key_row_to_record(row) for row in rows]
        return {
            "keys": keys,
            "total": len(keys),
        }

    def revoke_api_key(self, api_key_id: str) -> dict[str, Any] | None:
        timestamp = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE api_keys
                SET revoked_at = COALESCE(revoked_at, ?)
                WHERE id = ?
                """,
                (timestamp, api_key_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT
                    id,
                    name,
                    scope,
                    created_at,
                    last_used_at,
                    revoked_at,
                    rate_limit_requests,
                    rate_limit_window_seconds
                FROM api_keys
                WHERE id = ?
                """,
                (api_key_id,),
            ).fetchone()

        return self._api_key_row_to_record(row) if row is not None else None

    def delete_api_key(self, api_key_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, revoked_at FROM api_keys WHERE id = ?",
                (api_key_id,),
            ).fetchone()
            if row is None:
                return None
            if row["revoked_at"] is None:
                raise ApiError(
                    "API key must be revoked before deletion",
                    error_code="api_key_not_revoked",
                    status_code=409,
                )
            connection.execute(
                "DELETE FROM api_keys WHERE id = ?",
                (api_key_id,),
            )

        return {
            "id": api_key_id,
            "deleted": True,
        }

    def create_webhook_subscription(
        self,
        *,
        name: str,
        target_url: str,
        secret: str,
        format: str,
        event_filter: list[str],
        scope: str,
        api_key_id: str | None = None,
    ) -> dict[str, Any]:
        if scope == "api_key" and not api_key_id:
            raise ApiError("api_key_id is required for api_key scope", error_code="webhook_api_key_required")
        if scope == "global" and api_key_id is not None:
            raise ApiError("api_key_id is not allowed for global scope", error_code="webhook_scope_invalid")

        subscription_id = str(uuid.uuid4())
        timestamp = datetime.now(UTC).isoformat()
        normalized_event_filter = [value for value in event_filter if value]

        with self._connect() as connection:
            if api_key_id is not None:
                key_row = connection.execute(
                    "SELECT 1 FROM api_keys WHERE id = ?",
                    (api_key_id,),
                ).fetchone()
                if key_row is None:
                    raise ApiError("API key not found", error_code="api_key_not_found", status_code=404)
            connection.execute(
                """
                INSERT INTO webhook_subscriptions (
                    id,
                    name,
                    target_url,
                    secret,
                    format,
                    event_filter,
                    scope,
                    api_key_id,
                    created_at,
                    updated_at,
                    last_delivered_at,
                    last_error_at,
                    enabled
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 1)
                """,
                (
                    subscription_id,
                    name,
                    target_url,
                    secret,
                    format,
                    json.dumps(normalized_event_filter),
                    scope,
                    api_key_id,
                    timestamp,
                    timestamp,
                ),
            )

        subscription = self.get_webhook_subscription(subscription_id, include_secret=True)
        if subscription is None:
            raise ApiError("Webhook subscription not found", error_code="webhook_not_found", status_code=404)
        return subscription

    def list_webhook_subscriptions(self, *, include_secret: bool = False) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    name,
                    target_url,
                    secret,
                    format,
                    event_filter,
                    scope,
                    api_key_id,
                    created_at,
                    updated_at,
                    last_delivered_at,
                    last_error_at,
                    enabled
                FROM webhook_subscriptions
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()

        subscriptions = [
            self._webhook_subscription_row_to_record(row, include_secret=include_secret)
            for row in rows
        ]
        return {
            "subscriptions": subscriptions,
            "total": len(subscriptions),
        }

    def get_webhook_subscription(self, subscription_id: str, *, include_secret: bool = False) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    name,
                    target_url,
                    secret,
                    format,
                    event_filter,
                    scope,
                    api_key_id,
                    created_at,
                    updated_at,
                    last_delivered_at,
                    last_error_at,
                    enabled
                FROM webhook_subscriptions
                WHERE id = ?
                """,
                (subscription_id,),
            ).fetchone()

        if row is None:
            return None
        return self._webhook_subscription_row_to_record(row, include_secret=include_secret)

    def update_webhook_subscription(
        self,
        subscription_id: str,
        *,
        target_url: str | None = None,
        event_filter: list[str] | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any] | None:
        updates: list[str] = []
        params: list[Any] = []

        if target_url is not None:
            updates.append("target_url = ?")
            params.append(target_url)
        if event_filter is not None:
            updates.append("event_filter = ?")
            params.append(json.dumps([value for value in event_filter if value]))
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(1 if enabled else 0)

        if not updates:
            return self.get_webhook_subscription(subscription_id)

        timestamp = datetime.now(UTC).isoformat()
        updates.append("updated_at = ?")
        params.append(timestamp)
        params.append(subscription_id)

        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE webhook_subscriptions
                SET {", ".join(updates)}
                WHERE id = ?
                """,
                params,
            )
            if cursor.rowcount == 0:
                return None

        return self.get_webhook_subscription(subscription_id)

    def delete_webhook_subscription(self, subscription_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM webhook_subscriptions WHERE id = ?",
                (subscription_id,),
            )

        if cursor.rowcount == 0:
            return None
        return {"id": subscription_id, "deleted": True}

    def list_matching_webhook_subscriptions(
        self,
        *,
        event_type: str,
        key_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    name,
                    target_url,
                    secret,
                    format,
                    event_filter,
                    scope,
                    api_key_id,
                    created_at,
                    updated_at,
                    last_delivered_at,
                    last_error_at,
                    enabled
                FROM webhook_subscriptions
                WHERE enabled = 1
                ORDER BY created_at ASC, id ASC
                """
            ).fetchall()

        subscriptions: list[dict[str, Any]] = []
        for row in rows:
            subscription = self._webhook_subscription_row_to_record(row, include_secret=True)
            event_filter = subscription["event_filter"]
            if event_filter and event_type not in event_filter:
                continue
            if subscription["scope"] == "api_key":
                if key_id is None or subscription["api_key_id"] != key_id:
                    continue
            subscriptions.append(subscription)
        return subscriptions

    def create_webhook_delivery(
        self,
        *,
        subscription_id: str,
        event_id: int,
        status: str = "pending",
    ) -> dict[str, Any]:
        delivery_id = str(uuid.uuid4())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO webhook_deliveries (
                    id,
                    subscription_id,
                    event_id,
                    status,
                    attempt_count,
                    last_attempt_at,
                    delivered_at,
                    response_code,
                    response_body,
                    error_message
                )
                VALUES (?, ?, ?, ?, 0, NULL, NULL, NULL, NULL, NULL)
                """,
                (delivery_id, subscription_id, event_id, status),
            )

        delivery = self.get_webhook_delivery(delivery_id)
        if delivery is None:
            raise ApiError("Webhook delivery not found", error_code="webhook_delivery_not_found", status_code=404)
        return delivery

    def get_webhook_delivery(self, delivery_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    subscription_id,
                    event_id,
                    status,
                    attempt_count,
                    last_attempt_at,
                    delivered_at,
                    response_code,
                    response_body,
                    error_message
                FROM webhook_deliveries
                WHERE id = ?
                """,
                (delivery_id,),
            ).fetchone()

        if row is None:
            return None
        return self._webhook_delivery_row_to_record(row)

    def update_webhook_delivery(
        self,
        delivery_id: str,
        *,
        subscription_id: str,
        status: str,
        response_code: int | None = None,
        response_body: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any] | None:
        timestamp = datetime.now(UTC).isoformat()
        truncated_body = response_body[:2048] if response_body else None

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE webhook_deliveries
                SET
                    status = ?,
                    attempt_count = attempt_count + 1,
                    last_attempt_at = ?,
                    delivered_at = ?,
                    response_code = ?,
                    response_body = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (
                    status,
                    timestamp,
                    timestamp if status == "delivered" else None,
                    response_code,
                    truncated_body,
                    error_message,
                    delivery_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
            if status == "delivered":
                connection.execute(
                    """
                    UPDATE webhook_subscriptions
                    SET last_delivered_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (timestamp, timestamp, subscription_id),
                )
            elif status in {"failed", "retrying"}:
                connection.execute(
                    """
                    UPDATE webhook_subscriptions
                    SET last_error_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (timestamp, timestamp, subscription_id),
                )

        return self.get_webhook_delivery(delivery_id)

    def list_webhook_deliveries(
        self,
        subscription_id: str,
        *,
        limit: int = 50,
        status: str | None = None,
    ) -> dict[str, Any]:
        normalized_limit = max(1, min(int(limit), 200))
        where_clauses = ["subscription_id = ?"]
        params: list[Any] = [subscription_id]
        if status:
            where_clauses.append("status = ?")
            params.append(status)
        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        with self._connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM webhook_deliveries {where_sql}",
                    params,
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    subscription_id,
                    event_id,
                    status,
                    attempt_count,
                    last_attempt_at,
                    delivered_at,
                    response_code,
                    response_body,
                    error_message
                FROM webhook_deliveries
                {where_sql}
                ORDER BY COALESCE(last_attempt_at, delivered_at) DESC, id DESC
                LIMIT ?
                """,
                [*params, normalized_limit],
            ).fetchall()

        deliveries = [self._webhook_delivery_row_to_record(row) for row in rows]
        return {
            "deliveries": deliveries,
            "total": total,
        }

    def authenticate_api_key(self, plaintext_key: str) -> dict[str, Any] | None:
        key_hash = self.build_api_key_hash(plaintext_key)
        last_used_at = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    name,
                    scope,
                    created_at,
                    last_used_at,
                    revoked_at,
                    rate_limit_requests,
                    rate_limit_window_seconds
                FROM api_keys
                WHERE key_hash = ? AND revoked_at IS NULL
                """,
                (key_hash,),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                (last_used_at, row["id"]),
            )
            row = connection.execute(
                """
                SELECT
                    id,
                    name,
                    scope,
                    created_at,
                    last_used_at,
                    revoked_at,
                    rate_limit_requests,
                    rate_limit_window_seconds
                FROM api_keys
                WHERE id = ?
                """,
                (row["id"],),
            ).fetchone()

        return self._api_key_row_to_record(row) if row is not None else None

    def log_audit_entry(
        self,
        *,
        action: str,
        key_id: str | None = None,
        actor: str,
        request_id: str | None,
        ip_address: str | None,
        project_id: str | None = None,
        project_name: str | None = None,
        payload_diff: dict[str, list[Any]] | None = None,
        ts: str | None = None,
        dispatch_webhooks: bool = True,
    ) -> dict[str, Any]:
        timestamp = ts or datetime.now(UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO audit_log (
                    ts,
                    action,
                    project_id,
                    project_name,
                    key_id,
                    actor,
                    request_id,
                    payload_diff,
                    ip_address
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                (
                    timestamp,
                    action,
                    project_id,
                    project_name,
                    key_id,
                    actor,
                    request_id,
                    json.dumps(payload_diff) if payload_diff else None,
                    ip_address,
                ),
            )
            inserted = cursor.fetchone()
            inserted_id = inserted["id"] if inserted is not None else None
            row = connection.execute(
                """
                SELECT id, ts, action, project_id, project_name, key_id, actor, request_id, payload_diff, ip_address
                FROM audit_log
                WHERE id = ?
                """,
                (inserted_id,),
            ).fetchone()

        if row is None:
            raise ApiError("Audit event not found", error_code="audit_event_not_found", status_code=500)
        event = self._audit_row_to_record(row)
        if dispatch_webhooks and self.webhook_service is not None:
            try:
                self.webhook_service.dispatch_audit_event(event)
            except Exception:
                pass
        return event

    def list_audit_entries(
        self,
        *,
        project_id: str | None = None,
        key_id: str | None = None,
        action: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        normalized_limit = max(1, min(int(limit), 500))
        where_clauses: list[str] = []
        params: list[Any] = []
        if project_id:
            where_clauses.append("project_id = ?")
            params.append(project_id)
        if key_id:
            where_clauses.append("key_id = ?")
            params.append(key_id)
        if action:
            where_clauses.append("action = ?")
            params.append(action)
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        with self._connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM audit_log {where_sql}",
                    params,
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT id, ts, action, project_id, project_name, key_id, actor, request_id, payload_diff, ip_address
                FROM audit_log
                {where_sql}
                ORDER BY ts DESC, id DESC
                LIMIT ?
                """,
                [*params, normalized_limit],
            ).fetchall()

        entries = []
        for row in rows:
            entries.append(self._audit_row_to_record(row))
        return {
            "entries": entries,
            "total": total,
        }

    def export_audit_entries_csv(
        self,
        *,
        project_id: str | None = None,
        key_id: str | None = None,
        action: str | None = None,
    ) -> str:
        audit_log = self.list_audit_entries(project_id=project_id, key_id=key_id, action=action, limit=500)
        buffer = StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(
            ["ts", "action", "project_id", "project_name", "actor", "key_id", "request_id", "payload_diff", "ip_address"]
        )
        for entry in audit_log["entries"]:
            writer.writerow([
                entry["ts"],
                entry["action"],
                entry.get("project_id") or "",
                entry.get("project_name") or "",
                entry.get("actor") or "",
                entry.get("key_id") or "",
                entry.get("request_id") or "",
                json.dumps(entry["payload_diff"], sort_keys=True) if entry.get("payload_diff") else "",
                entry.get("ip_address") or "",
            ])
        return buffer.getvalue()

    def get_project_history(
        self,
        project_id: str,
        *,
        analysis_limit: int = 20,
        analysis_offset: int = 0,
        export_limit: int = 20,
        export_offset: int = 0,
    ) -> dict[str, Any] | None:
        analysis_limit = self._normalize_history_limit(analysis_limit)
        analysis_offset = self._normalize_history_offset(analysis_offset)
        export_limit = self._normalize_history_limit(export_limit)
        export_offset = self._normalize_history_offset(export_offset)

        with self._connect() as connection:
            project_row = connection.execute(
                "SELECT 1 FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if project_row is None:
                return None

            analysis_total = connection.execute(
                """
                SELECT COUNT(*)
                FROM analysis_runs
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()[0]
            export_total = connection.execute(
                """
                SELECT COUNT(*)
                FROM export_events
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()[0]
            analysis_rows = connection.execute(
                """
                SELECT id, project_id, analysis_json, created_at
                FROM analysis_runs
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                OFFSET ?
                """,
                (project_id, analysis_limit, analysis_offset),
            ).fetchall()
            export_rows = connection.execute(
                """
                SELECT id, project_id, analysis_run_id, format, created_at
                FROM export_events
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                OFFSET ?
                """,
                (project_id, export_limit, export_offset),
            ).fetchall()

        return {
            "project_id": project_id,
            "analysis_total": analysis_total,
            "analysis_limit": analysis_limit,
            "analysis_offset": analysis_offset,
            "export_total": export_total,
            "export_limit": export_limit,
            "export_offset": export_offset,
            "analysis_runs": [self._analysis_row_to_record(row) for row in analysis_rows],
            "export_events": [self._export_row_to_record(row) for row in export_rows],
        }

    def get_project_revisions(
        self,
        project_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any] | None:
        limit = self._normalize_history_limit(limit)
        offset = self._normalize_history_offset(offset)

        with self._connect() as connection:
            project_row = connection.execute(
                "SELECT 1 FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if project_row is None:
                return None

            total = connection.execute(
                """
                SELECT COUNT(*)
                FROM project_revisions
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()[0]
            revision_rows = connection.execute(
                """
                SELECT id, project_id, payload_json, source, created_at
                FROM project_revisions
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                OFFSET ?
                """,
                (project_id, limit, offset),
            ).fetchall()

        return {
            "project_id": project_id,
            "total": total,
            "limit": limit,
            "offset": offset,
            "revisions": [self._revision_row_to_record(row) for row in revision_rows],
        }

    def get_analysis_run(self, project_id: str, analysis_run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, project_id, analysis_json, created_at
                FROM analysis_runs
                WHERE project_id = ? AND id = ?
                """,
                (project_id, analysis_run_id),
            ).fetchone()

        if row is None:
            return None

        return self._analysis_row_to_record(row)

    def get_latest_analysis_run(self, project_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, project_id, analysis_json, created_at
                FROM analysis_runs
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()

        if row is None:
            return None

        return self._analysis_row_to_record(row)

    def get_diagnostics_summary(self) -> dict[str, Any]:
        disk_free_bytes = shutil.disk_usage(self.db_path.parent).free
        db_size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
        write_probe_ok, write_probe_detail = self._run_write_probe()

        with self._connect() as connection:
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            synchronous_raw = connection.execute("PRAGMA synchronous").fetchone()[0]
            sqlite_user_version = connection.execute("PRAGMA user_version").fetchone()[0]
            projects_total = connection.execute(
                "SELECT COUNT(*) FROM projects WHERE archived_at IS NULL"
            ).fetchone()[0]
            archived_projects_total = connection.execute(
                "SELECT COUNT(*) FROM projects WHERE archived_at IS NOT NULL"
            ).fetchone()[0]
            analysis_runs_total = connection.execute(
                "SELECT COUNT(*) FROM analysis_runs"
            ).fetchone()[0]
            export_events_total = connection.execute(
                "SELECT COUNT(*) FROM export_events"
            ).fetchone()[0]
            project_revisions_total = connection.execute(
                "SELECT COUNT(*) FROM project_revisions"
            ).fetchone()[0]
            latest_project_updated_at_row = connection.execute(
                "SELECT MAX(updated_at) AS updated_at FROM projects"
            ).fetchone()

        synchronous_labels = {
            0: "OFF",
            1: "NORMAL",
            2: "FULL",
            3: "EXTRA",
        }
        synchronous = synchronous_labels.get(synchronous_raw, str(synchronous_raw))

        return {
            "db_path": str(self.db_path),
            "db_parent_path": str(self.db_path.parent),
            "db_exists": self.db_path.exists(),
            "db_size_bytes": db_size_bytes,
            "disk_free_bytes": disk_free_bytes,
            "schema_version": self.schema_version,
            "sqlite_user_version": sqlite_user_version,
            "busy_timeout_ms": self.busy_timeout_ms,
            "journal_mode": str(journal_mode).upper(),
            "synchronous": synchronous,
            "write_probe_ok": write_probe_ok,
            "write_probe_detail": write_probe_detail,
            "projects_total": projects_total,
            "archived_projects_total": archived_projects_total,
            "analysis_runs_total": analysis_runs_total,
            "export_events_total": export_events_total,
            "project_revisions_total": project_revisions_total,
            "workspace_bundle_schema_version": self.workspace_schema_version,
            "workspace_signature_enabled": self.workspace_signing_key is not None,
            "latest_project_updated_at": (
                latest_project_updated_at_row["updated_at"]
                if latest_project_updated_at_row is not None
                else None
            ),
        }

    def _run_write_probe(self) -> tuple[bool, str]:
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("ROLLBACK")
            return True, "BEGIN IMMEDIATE succeeded"
        except sqlite3.Error as exc:
            return False, str(exc)

    def export_workspace(self) -> dict[str, Any]:
        with self._connect() as connection:
            project_rows = connection.execute(
                f"""
                SELECT {self.project_select_columns}
                FROM projects
                ORDER BY created_at ASC, id ASC
                """
            ).fetchall()
            analysis_rows = connection.execute(
                """
                SELECT id, project_id, analysis_json, created_at
                FROM analysis_runs
                ORDER BY created_at ASC, id ASC
                """
            ).fetchall()
            export_rows = connection.execute(
                """
                SELECT id, project_id, analysis_run_id, format, created_at
                FROM export_events
                ORDER BY created_at ASC, id ASC
                """
            ).fetchall()
            revision_rows = connection.execute(
                """
                SELECT id, project_id, payload_json, source, created_at
                FROM project_revisions
                ORDER BY created_at ASC, id ASC
                """
            ).fetchall()

        bundle = {
            "schema_version": self.workspace_schema_version,
            "generated_at": datetime.now(UTC).isoformat(),
            "projects": [self._project_row_to_workspace_record(row) for row in project_rows],
            "analysis_runs": [self._analysis_row_to_workspace_record(row) for row in analysis_rows],
            "export_events": [self._export_row_to_record(row) for row in export_rows],
            "project_revisions": [self._revision_row_to_record(row) for row in revision_rows],
        }
        bundle["integrity"] = self._build_workspace_integrity(bundle)
        return bundle

    @classmethod
    def _workspace_integrity_source(cls, bundle: dict[str, Any]) -> dict[str, Any]:
        def normalize_project_payload(payload: object) -> object:
            if not isinstance(payload, dict):
                return payload
            try:
                return ExperimentInput.model_validate(payload).model_dump()
            except ValidationError:
                return payload

        def normalize_workspace_project(record: object) -> object:
            if not isinstance(record, dict):
                return record
            normalized_record = dict(record)
            normalized_record["payload"] = normalize_project_payload(normalized_record.get("payload"))
            return normalized_record

        return {
            "schema_version": bundle.get("schema_version"),
            "generated_at": bundle.get("generated_at"),
            "projects": [normalize_workspace_project(project) for project in bundle.get("projects", [])],
            "analysis_runs": bundle.get("analysis_runs", []),
            "export_events": bundle.get("export_events", []),
            "project_revisions": [
                normalize_workspace_project(revision) for revision in bundle.get("project_revisions", [])
            ],
        }

    @classmethod
    def _workspace_counts(cls, bundle: dict[str, Any]) -> dict[str, int]:
        source = cls._workspace_integrity_source(bundle)
        return {
            "projects": len(source["projects"]),
            "analysis_runs": len(source["analysis_runs"]),
            "export_events": len(source["export_events"]),
            "project_revisions": len(source["project_revisions"]),
        }

    @classmethod
    def _workspace_checksum(cls, bundle: dict[str, Any]) -> str:
        serialized = json.dumps(
            cls._workspace_integrity_source(bundle),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def _workspace_signature(cls, bundle: dict[str, Any], signing_key: str) -> str:
        serialized = json.dumps(
            cls._workspace_integrity_source(bundle),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hmac.new(signing_key.encode("utf-8"), serialized.encode("utf-8"), hashlib.sha256).hexdigest()

    def _build_workspace_integrity(self, bundle: dict[str, Any]) -> dict[str, Any]:
        integrity = {
            "counts": self._workspace_counts(bundle),
            "checksum_sha256": self._workspace_checksum(bundle),
        }
        if self.workspace_signing_key:
            integrity["signature_hmac_sha256"] = self._workspace_signature(bundle, self.workspace_signing_key)
        return integrity

    def _validate_workspace_bundle(self, bundle: dict[str, Any]) -> bool:
        schema_version = int(bundle.get("schema_version", 1))
        if schema_version not in {1, 2, 3}:
            raise ApiError(
                "Unsupported workspace bundle schema_version",
                error_code="workspace_schema_unsupported",
            )

        integrity = bundle.get("integrity")
        if integrity is None:
            if schema_version >= 2:
                raise ApiError(
                    "Workspace bundle integrity block is required for schema_version 2 or later",
                    error_code="workspace_integrity_required",
                )
            return False

        actual_counts = self._workspace_counts(bundle)
        expected_counts = integrity.get("counts", {})
        if {
            "projects": int(expected_counts.get("projects", -1)),
            "analysis_runs": int(expected_counts.get("analysis_runs", -1)),
            "export_events": int(expected_counts.get("export_events", -1)),
            "project_revisions": int(expected_counts.get("project_revisions", -1)),
        } != actual_counts:
            raise ApiError(
                "Workspace bundle integrity counts mismatch",
                error_code="workspace_integrity_counts_mismatch",
            )

        expected_checksum = str(integrity.get("checksum_sha256") or "").strip()
        if not expected_checksum:
            raise ApiError(
                "Workspace bundle checksum is missing",
                error_code="workspace_integrity_checksum_missing",
            )
        if expected_checksum != self._workspace_checksum(bundle):
            raise ApiError(
                "Workspace bundle checksum mismatch",
                error_code="workspace_integrity_checksum_mismatch",
            )

        expected_signature = str(integrity.get("signature_hmac_sha256") or "").strip()
        if self.workspace_signing_key:
            if not expected_signature:
                raise ApiError(
                    "Workspace bundle signature is required on this runtime",
                    error_code="workspace_signature_required",
                )
            actual_signature = self._workspace_signature(bundle, self.workspace_signing_key)
            if not hmac.compare_digest(expected_signature, actual_signature):
                raise ApiError(
                    "Workspace bundle signature mismatch",
                    error_code="workspace_signature_mismatch",
                )
            signature_verified = True
        else:
            if expected_signature:
                raise ApiError(
                    "Workspace bundle signature cannot be verified on this runtime",
                    error_code="workspace_signature_verification_unavailable",
                )
            signature_verified = False

        project_ids = [str(project.get("id", "")) for project in bundle.get("projects", [])]
        analysis_run_ids = [str(run.get("id", "")) for run in bundle.get("analysis_runs", [])]
        revision_ids = [str(revision.get("id", "")) for revision in bundle.get("project_revisions", [])]
        for label, identifiers in (
            ("project", project_ids),
            ("analysis_run", analysis_run_ids),
            ("project_revision", revision_ids),
        ):
            cleaned = [identifier for identifier in identifiers if identifier]
            if len(cleaned) != len(set(cleaned)):
                raise ApiError(
                    f"Workspace bundle contains duplicate {label} ids",
                    error_code=f"workspace_duplicate_{label}_id",
                )
        return signature_verified

    def validate_workspace_bundle(self, bundle: dict[str, Any]) -> dict[str, Any]:
        signature_verified = self._validate_workspace_bundle(bundle)
        imported_projects = bundle.get("projects", [])
        imported_analysis_runs = bundle.get("analysis_runs", [])
        imported_export_events = bundle.get("export_events", [])
        imported_project_revisions = bundle.get("project_revisions", [])

        project_ids = {project["id"] for project in imported_projects}
        analysis_run_ids = {analysis_run["id"] for analysis_run in imported_analysis_runs}

        for analysis_run in imported_analysis_runs:
            if analysis_run["project_id"] not in project_ids:
                raise ApiError(
                    "Workspace bundle references an unknown project in analysis_runs",
                    error_code="workspace_analysis_unknown_project",
                )

        for export_event in imported_export_events:
            if export_event["project_id"] not in project_ids:
                raise ApiError(
                    "Workspace bundle references an unknown project in export_events",
                    error_code="workspace_export_unknown_project",
                )
            analysis_run_id = export_event.get("analysis_run_id")
            if analysis_run_id and analysis_run_id not in analysis_run_ids:
                raise ApiError(
                    "Workspace bundle references an unknown analysis run in export_events",
                    error_code="workspace_export_unknown_analysis_run",
                )

        for revision in imported_project_revisions:
            if revision["project_id"] not in project_ids:
                raise ApiError(
                    "Workspace bundle references an unknown project in project_revisions",
                    error_code="workspace_revision_unknown_project",
                )

        integrity = self._build_workspace_integrity(bundle)
        return {
            "status": "valid",
            "schema_version": int(bundle.get("schema_version", 1)),
            "counts": integrity["counts"],
            "checksum_sha256": integrity["checksum_sha256"],
            "signature_verified": signature_verified,
        }

    def import_workspace(self, bundle: dict[str, Any]) -> dict[str, Any]:
        self.validate_workspace_bundle(bundle)
        imported_projects = bundle.get("projects", [])
        imported_analysis_runs = bundle.get("analysis_runs", [])
        imported_export_events = bundle.get("export_events", [])
        imported_project_revisions = bundle.get("project_revisions", [])

        project_id_map = {
            project["id"]: str(uuid.uuid4())
            for project in imported_projects
        }
        analysis_run_id_map = {
            analysis_run["id"]: str(uuid.uuid4())
            for analysis_run in imported_analysis_runs
        }
        revision_id_map = {
            revision["id"]: str(uuid.uuid4())
            for revision in imported_project_revisions
        }
        projects_with_imported_revisions = {
            revision["project_id"]
            for revision in imported_project_revisions
        }
        imported_revision_count = 0

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for project in imported_projects:
                old_project_id = project["id"]
                connection.execute(
                    """
                    INSERT INTO projects (
                        id,
                        project_name,
                        payload_json,
                        payload_schema_version,
                        archived_at,
                        last_analysis_at,
                        last_analysis_run_id,
                        last_exported_at,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id_map[old_project_id],
                        project["project_name"],
                        json.dumps(project["payload"]),
                        int(project.get("payload_schema_version", self.payload_schema_version)),
                        project.get("archived_at"),
                        project.get("last_analysis_at"),
                        analysis_run_id_map.get(project.get("last_analysis_run_id")),
                        project.get("last_exported_at"),
                        project["created_at"],
                        project["updated_at"],
                    ),
                )
                if old_project_id not in projects_with_imported_revisions:
                    self._create_revision(
                        connection,
                        project_id_map[old_project_id],
                        project["payload"],
                        "workspace_import",
                        project.get("updated_at") or project["created_at"],
                    )
                    imported_revision_count += 1

            for analysis_run in imported_analysis_runs:
                new_project_id = project_id_map.get(analysis_run["project_id"])
                connection.execute(
                    """
                    INSERT INTO analysis_runs (id, project_id, analysis_json, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        analysis_run_id_map[analysis_run["id"]],
                        new_project_id,
                        json.dumps(analysis_run["analysis"]),
                        analysis_run["created_at"],
                    ),
                )

            for export_event in imported_export_events:
                new_project_id = project_id_map.get(export_event["project_id"])
                old_analysis_run_id = export_event.get("analysis_run_id")
                new_analysis_run_id = analysis_run_id_map.get(old_analysis_run_id) if old_analysis_run_id else None
                connection.execute(
                    """
                    INSERT INTO export_events (id, project_id, analysis_run_id, format, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        new_project_id,
                        new_analysis_run_id,
                        export_event["format"],
                        export_event["created_at"],
                    ),
                )

            for revision in imported_project_revisions:
                # Revisions in a valid bundle always reference an imported project,
                # so the lookup resolves to a freshly minted project id.
                new_project_id = cast("str", project_id_map.get(revision["project_id"]))
                self._create_revision(
                    connection,
                    new_project_id,
                    revision["payload"],
                    revision["source"],
                    revision["created_at"],
                    revision_id=revision_id_map[revision["id"]],
                )
                imported_revision_count += 1

        return {
            "status": "imported",
            "imported_projects": len(imported_projects),
            "imported_analysis_runs": len(imported_analysis_runs),
            "imported_export_events": len(imported_export_events),
            "imported_project_revisions": imported_revision_count,
        }

    def archive_project(self, project_id: str) -> dict[str, Any] | None:
        timestamp = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            if not self._project_exists(connection, project_id):
                return None
            cursor = connection.execute(
                """
                UPDATE projects
                SET
                    archived_at = COALESCE(archived_at, ?),
                    updated_at = CASE WHEN archived_at IS NULL THEN ? ELSE updated_at END
                WHERE id = ?
                """,
                (timestamp, timestamp, project_id),
            )

        if cursor.rowcount == 0:
            return None

        archived_project = self.get_project(project_id, include_archived=True)
        if archived_project is None:
            return None

        return {
            "id": project_id,
            "archived": True,
            "archived_at": archived_project.get("archived_at"),
        }

    def delete_project(self, project_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            if not self._project_exists(connection, project_id):
                return None
            cursor = connection.execute(
                "DELETE FROM projects WHERE id = ?",
                (project_id,),
            )

        if cursor.rowcount == 0:
            return None

        return {
            "id": project_id,
            "deleted": True,
        }

    def restore_project(self, project_id: str) -> dict[str, Any] | None:
        timestamp = datetime.now(UTC).isoformat()

        with self._connect() as connection:
            if not self._project_exists(connection, project_id):
                return None
            cursor = connection.execute(
                """
                UPDATE projects
                SET archived_at = NULL, updated_at = ?
                WHERE id = ? AND archived_at IS NOT NULL
                """,
                (timestamp, project_id),
            )

        if cursor.rowcount == 0:
            return self.get_project(project_id, include_archived=True)

        return self.get_project(project_id, include_archived=True)

    # --- Execution layer (Phase C): exposure / conversion ingestion -----------------

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


class _PostgresRow(dict[str, Any]):
    def __init__(self, mapping: dict[str, Any]) -> None:
        super().__init__(mapping)
        self._ordered_values = tuple(mapping.values())

    def __getitem__(self, key: object) -> Any:
        if isinstance(key, int):
            return self._ordered_values[key]
        return super().__getitem__(cast("str", key))


class _PostgresCursorResult:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor
        self.rowcount = cursor.rowcount
        self.lastrowid = None

    @staticmethod
    def _wrap_row(row: Any) -> Any:
        if row is None or not isinstance(row, dict):
            return row
        return _PostgresRow(row)

    def fetchone(self) -> Any:
        return self._wrap_row(self._cursor.fetchone())

    def fetchall(self) -> list[Any]:
        return [self._wrap_row(row) for row in self._cursor.fetchall()]


class _PooledPostgresConnection:
    def __init__(self, backend: "PostgresBackend") -> None:
        self._backend = backend
        self._connection: Any | None = None

    def __enter__(self) -> "_PooledPostgresConnection":
        connection: Any = self._backend._pool.getconn()
        connection.row_factory = dict_row
        self._connection = connection
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._connection is None:
            return
        try:
            if exc_type is None:
                self._connection.commit()
            else:
                self._connection.rollback()
        finally:
            self._backend._pool.putconn(self._connection)
            self._connection = None

    def execute(self, sql: str, params: Any = None) -> _PostgresCursorResult:
        if self._connection is None:
            raise RuntimeError("Postgres connection is not open")
        cursor = self._connection.execute(
            self._backend._translate_sql(sql),
            self._backend._adapt_params(params),
        )
        return _PostgresCursorResult(cursor)


class PostgresBackend(SQLiteBackend):
    backend_name = "postgres"
    supports_snapshots = False

    def __init__(
        self,
        database_url: str,
        *,
        pool_size: int = 10,
        workspace_signing_key: str | None = None,
        **_: Any,
    ) -> None:
        self.database_url = database_url
        self.db_path = Path(".")
        self.pool_size = max(1, int(pool_size))
        self.busy_timeout_ms = 0
        self.journal_mode = "POSTGRES"
        self.synchronous = "READ COMMITTED"
        self.workspace_signing_key = workspace_signing_key.strip() if workspace_signing_key else None
        self.webhook_service: Any | None = None
        self._pool = ConnectionPool(
            database_url,
            min_size=1,
            max_size=self.pool_size,
            open=False,
            kwargs={"autocommit": False, "row_factory": dict_row},
        )
        self._pool.open(wait=True)
        self._init_db()

    def close(self) -> None:
        self._pool.close()

    def _connect(self) -> _PooledPostgresConnection:  # type: ignore[override]  # PostgresBackend reuses SQLiteBackend's query methods with a duck-typed pooled connection that mirrors the sqlite3.Connection context-manager + execute() surface used by those methods
        return _PooledPostgresConnection(self)

    @staticmethod
    def _json_extract_expression(column: str, *path: str) -> str:
        expression = column
        for part in path[:-1]:
            expression = f"{expression} -> '{part}'"
        return f"{expression} ->> '{path[-1]}'"

    @staticmethod
    def _adapt_param(value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped[:1] in "{[":
                try:
                    return Jsonb(json.loads(value))
                except json.JSONDecodeError:
                    return value
        return value

    def _adapt_params(self, params: Any) -> Any:
        if params is None:
            return None
        if isinstance(params, dict):
            return {key: self._adapt_param(value) for key, value in params.items()}
        if isinstance(params, (list, tuple)):
            return tuple(self._adapt_param(value) for value in params)
        return self._adapt_param(params)

    @staticmethod
    def _translate_sql(sql: str) -> str:
        translated = sql.replace("BEGIN IMMEDIATE", "BEGIN")
        return translated.replace("?", "%s")

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    payload_json JSONB NOT NULL,
                    payload_schema_version INTEGER NOT NULL DEFAULT 1,
                    archived_at TEXT,
                    last_analysis_json JSONB,
                    last_analysis_at TEXT,
                    last_analysis_run_id TEXT,
                    last_exported_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    analysis_json JSONB NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_analysis_runs_project_created
                ON analysis_runs (project_id, created_at DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS export_events (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    analysis_run_id TEXT,
                    format TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY(analysis_run_id) REFERENCES analysis_runs(id) ON DELETE SET NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_export_events_project_created
                ON export_events (project_id, created_at DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS project_revisions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    payload_json JSONB NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_project_revisions_project_created
                ON project_revisions (project_id, created_at DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    ts TEXT NOT NULL,
                    action TEXT NOT NULL,
                    project_id TEXT,
                    project_name TEXT,
                    key_id TEXT,
                    actor TEXT,
                    request_id TEXT,
                    payload_diff JSONB,
                    ip_address TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_log_created
                ON audit_log (ts DESC, id DESC)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_log_project
                ON audit_log (project_id, ts DESC, id DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    key_hash TEXT NOT NULL UNIQUE,
                    scope TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    revoked_at TEXT,
                    rate_limit_requests INTEGER,
                    rate_limit_window_seconds INTEGER
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_api_keys_scope_active
                ON api_keys (scope, revoked_at, created_at DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS webhook_subscriptions (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    target_url TEXT NOT NULL,
                    secret TEXT NOT NULL,
                    format TEXT NOT NULL,
                    event_filter JSONB NOT NULL DEFAULT '[]'::jsonb,
                    scope TEXT NOT NULL,
                    api_key_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_delivered_at TEXT,
                    last_error_at TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    FOREIGN KEY(api_key_id) REFERENCES api_keys(id) ON DELETE SET NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_webhook_subscriptions_scope_enabled
                ON webhook_subscriptions (scope, enabled, updated_at DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS webhook_deliveries (
                    id TEXT PRIMARY KEY,
                    subscription_id TEXT NOT NULL,
                    event_id BIGINT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_attempt_at TEXT,
                    delivered_at TEXT,
                    response_code INTEGER,
                    response_body TEXT,
                    error_message TEXT,
                    FOREIGN KEY(subscription_id) REFERENCES webhook_subscriptions(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS slack_installations (
                    team_id TEXT PRIMARY KEY,
                    team_name TEXT,
                    bot_token TEXT NOT NULL,
                    user_token TEXT,
                    installed_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_slack_installations_updated
                ON slack_installations (updated_at DESC)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_subscription
                ON webhook_deliveries (subscription_id, status, delivered_at DESC, id DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS project_templates (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    built_in INTEGER NOT NULL DEFAULT 0,
                    tags_json JSONB NOT NULL,
                    payload_json JSONB NOT NULL,
                    usage_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_project_templates_usage
                ON project_templates (built_in DESC, usage_count DESC, updated_at DESC)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_projects_metric_type
                ON projects (((payload_json -> 'metrics' ->> 'metric_type')))
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS exposures (
                    id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    variation_index INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    UNIQUE(experiment_id, user_id),
                    FOREIGN KEY(experiment_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_exposures_experiment_variation
                ON exposures (experiment_id, variation_index)
                """
            )
            # Event-time semantics (P4.1) — Postgres mirror of the SQLite occurred_at column. Fresh
            # containers get it from here (CI provisions Postgres fresh, so no backfill is needed).
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversions (
                    id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    value REAL NOT NULL DEFAULT 1,
                    idempotency_key TEXT,
                    created_at TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    UNIQUE(experiment_id, idempotency_key),
                    FOREIGN KEY(experiment_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversions_experiment_metric
                ON conversions (experiment_id, metric)
                """
            )
            # Per-user conversion lookup index — Postgres mirror of the SQLite index. Speeds the
            # correlated per-user conversion join in the heavy live-read rollups (see the SQLite note).
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversions_experiment_user_metric
                ON conversions (experiment_id, user_id, metric)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pre_period_values (
                    id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    value REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(experiment_id, user_id),
                    FOREIGN KEY(experiment_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            # Multi-covariate CUPED (F3a) — Postgres mirror of the SQLite table. Fresh containers
            # get the table straight from here; the legacy-data backfill is SQLite-only (Postgres
            # is provisioned fresh in CI / has no in-project migration path).
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pre_period_covariates (
                    id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    covariate_name TEXT NOT NULL,
                    value REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(experiment_id, user_id, covariate_name),
                    FOREIGN KEY(experiment_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            # Post-stratification (F3b) — Postgres mirror of the SQLite ``user_strata`` table.
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_strata (
                    id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    stratum TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(experiment_id, user_id),
                    FOREIGN KEY(experiment_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_strata_experiment_stratum
                ON user_strata (experiment_id, stratum)
                """
            )
            # Identity resolution (P4.3) — Postgres mirror of the SQLite ``identity_map`` table.
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS identity_map (
                    id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    anonymous_id TEXT NOT NULL,
                    canonical_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(experiment_id, anonymous_id),
                    FOREIGN KEY(experiment_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_identity_map_experiment_anonymous
                ON identity_map (experiment_id, anonymous_id)
                """
            )
            # Bot / fraud filter (P4.4) — Postgres mirror of the SQLite ``excluded_users`` table.
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS excluded_users (
                    id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    exclusion_reason TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'manual',
                    created_at TEXT NOT NULL,
                    UNIQUE(experiment_id, user_id),
                    FOREIGN KEY(experiment_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_excluded_users_experiment
                ON excluded_users (experiment_id, user_id)
                """
            )

    def list_projects(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        archived_filter = "" if include_archived else "WHERE projects.archived_at IS NULL"
        hypothesis_expr = self._json_extract_expression("projects.payload_json", "hypothesis", "hypothesis_statement")
        metric_expr = self._json_extract_expression("projects.payload_json", "metrics", "metric_type")
        duration_expr = self._json_extract_expression(
            "analysis_json",
            "report",
            "calculations",
            "estimated_duration_days",
        )
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    projects.id,
                    projects.project_name,
                    {hypothesis_expr} AS hypothesis,
                    {metric_expr} AS metric_type,
                    (
                        SELECT ({duration_expr})::INTEGER
                        FROM analysis_runs
                        WHERE analysis_runs.project_id = projects.id
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1
                    ) AS duration_days,
                    projects.payload_schema_version,
                    projects.archived_at,
                    (
                        SELECT COUNT(*)
                        FROM project_revisions
                        WHERE project_revisions.project_id = projects.id
                    ) AS revision_count,
                    (
                        SELECT MAX(created_at)
                        FROM project_revisions
                        WHERE project_revisions.project_id = projects.id
                    ) AS last_revision_at,
                    projects.last_analysis_at,
                    projects.last_analysis_run_id,
                    projects.last_exported_at,
                    CASE WHEN projects.last_analysis_run_id IS NOT NULL THEN 1 ELSE 0 END AS has_analysis_snapshot,
                    CASE WHEN projects.archived_at IS NOT NULL THEN 1 ELSE 0 END AS is_archived,
                    projects.created_at,
                    projects.updated_at
                FROM projects
                {archived_filter}
                ORDER BY projects.updated_at DESC
                """
            ).fetchall()
        return [self._project_list_row_to_record(row) for row in rows]

    def query_projects(
        self,
        *,
        q: str | None = None,
        status: str = "active",
        metric_type: str = "all",
        sort_by: str = "updated_at",
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        normalized_query = q.strip().lower() if isinstance(q, str) else ""
        normalized_status = status if status in {"active", "archived", "all"} else "active"
        normalized_metric_type = metric_type if metric_type in {"binary", "continuous", "ratio", "all"} else "all"
        normalized_sort_by = sort_by if sort_by in {"created_at", "updated_at", "name", "duration_days"} else "updated_at"
        normalized_sort_dir = "ASC" if str(sort_dir).lower() == "asc" else "DESC"
        metric_expr = self._json_extract_expression("projects.payload_json", "metrics", "metric_type")
        hypothesis_expr = self._json_extract_expression("projects.payload_json", "hypothesis", "hypothesis_statement")
        change_expr = self._json_extract_expression("projects.payload_json", "hypothesis", "change_description")
        duration_expr = self._json_extract_expression(
            "analysis_json",
            "report",
            "calculations",
            "estimated_duration_days",
        )
        where_clauses: list[str] = []
        params: list[object] = []

        if normalized_status == "active":
            where_clauses.append("projects.archived_at IS NULL")
        elif normalized_status == "archived":
            where_clauses.append("projects.archived_at IS NOT NULL")

        if normalized_metric_type != "all":
            where_clauses.append(f"{metric_expr} = ?")
            params.append(normalized_metric_type)

        if normalized_query:
            like_pattern = f"%{normalized_query}%"
            where_clauses.append(
                f"""
                (
                    lower(projects.project_name) LIKE ?
                    OR lower(COALESCE({hypothesis_expr}, '')) LIKE ?
                    OR lower(COALESCE({change_expr}, '')) LIKE ?
                )
                """
            )
            params.extend([like_pattern, like_pattern, like_pattern])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        if normalized_sort_by == "name":
            order_sql = f"ORDER BY lower(projects.project_name) {normalized_sort_dir}, projects.updated_at DESC"
        elif normalized_sort_by == "duration_days":
            order_sql = f"ORDER BY duration_days IS NULL, duration_days {normalized_sort_dir}, projects.updated_at DESC"
        else:
            order_column = "projects.created_at" if normalized_sort_by == "created_at" else "projects.updated_at"
            order_sql = f"ORDER BY {order_column} {normalized_sort_dir}, projects.id DESC"

        with self._connect() as connection:
            total = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM projects
                {where_sql}
                """,
                params,
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT
                    projects.id,
                    projects.project_name,
                    {hypothesis_expr} AS hypothesis,
                    {metric_expr} AS metric_type,
                    (
                        SELECT ({duration_expr})::INTEGER
                        FROM analysis_runs
                        WHERE analysis_runs.project_id = projects.id
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1
                    ) AS duration_days,
                    projects.payload_schema_version,
                    projects.archived_at,
                    (
                        SELECT COUNT(*)
                        FROM project_revisions
                        WHERE project_revisions.project_id = projects.id
                    ) AS revision_count,
                    (
                        SELECT MAX(created_at)
                        FROM project_revisions
                        WHERE project_revisions.project_id = projects.id
                    ) AS last_revision_at,
                    projects.last_analysis_at,
                    projects.last_analysis_run_id,
                    projects.last_exported_at,
                    CASE WHEN projects.last_analysis_run_id IS NOT NULL THEN 1 ELSE 0 END AS has_analysis_snapshot,
                    CASE WHEN projects.archived_at IS NOT NULL THEN 1 ELSE 0 END AS is_archived,
                    projects.created_at,
                    projects.updated_at
                FROM projects
                {where_sql}
                {order_sql}
                LIMIT ?
                OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()

        return {
            "projects": [self._project_list_row_to_record(row) for row in rows],
            "total": int(total),
            "offset": offset,
            "limit": limit,
            "has_more": (offset + len(rows)) < int(total),
        }

    def list_templates(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, category, description, built_in, tags_json, payload_json, usage_count
                FROM project_templates
                ORDER BY built_in DESC, usage_count DESC, lower(name) ASC
                """
            ).fetchall()
        return [self._template_row_to_record(row) for row in rows]

    def log_audit_entry(
        self,
        *,
        action: str,
        key_id: str | None = None,
        actor: str,
        request_id: str | None,
        ip_address: str | None,
        project_id: str | None = None,
        project_name: str | None = None,
        payload_diff: dict[str, list[Any]] | None = None,
        ts: str | None = None,
        dispatch_webhooks: bool = True,
    ) -> dict[str, Any]:
        timestamp = ts or datetime.now(UTC).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO audit_log (
                    ts,
                    action,
                    project_id,
                    project_name,
                    key_id,
                    actor,
                    request_id,
                    payload_diff,
                    ip_address
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id, ts, action, project_id, project_name, key_id, actor, request_id, payload_diff, ip_address
                """,
                (
                    timestamp,
                    action,
                    project_id,
                    project_name,
                    key_id,
                    actor,
                    request_id,
                    json.dumps(payload_diff) if payload_diff else None,
                    ip_address,
                ),
            ).fetchone()

        if row is None:
            raise ApiError("Audit event not found", error_code="audit_event_not_found", status_code=500)
        event = self._audit_row_to_record(row)
        if dispatch_webhooks and self.webhook_service is not None:
            try:
                self.webhook_service.dispatch_audit_event(event)
            except Exception:
                pass
        return event

    def get_diagnostics_summary(self) -> dict[str, Any]:
        parsed = urlparse(self.database_url)
        write_probe_ok, write_probe_detail = self._run_write_probe()

        with self._connect() as connection:
            db_size_bytes = connection.execute(
                "SELECT pg_database_size(current_database()) AS db_size_bytes"
            ).fetchone()["db_size_bytes"]
            projects_total = connection.execute(
                "SELECT COUNT(*) FROM projects WHERE archived_at IS NULL"
            ).fetchone()[0]
            archived_projects_total = connection.execute(
                "SELECT COUNT(*) FROM projects WHERE archived_at IS NOT NULL"
            ).fetchone()[0]
            analysis_runs_total = connection.execute(
                "SELECT COUNT(*) FROM analysis_runs"
            ).fetchone()[0]
            export_events_total = connection.execute(
                "SELECT COUNT(*) FROM export_events"
            ).fetchone()[0]
            project_revisions_total = connection.execute(
                "SELECT COUNT(*) FROM project_revisions"
            ).fetchone()[0]
            latest_project_updated_at_row = connection.execute(
                "SELECT MAX(updated_at) AS updated_at FROM projects"
            ).fetchone()

        return {
            "db_path": self.database_url,
            "db_parent_path": parsed.netloc,
            "db_exists": True,
            "db_size_bytes": int(db_size_bytes),
            "disk_free_bytes": 0,
            "schema_version": self.schema_version,
            "sqlite_user_version": self.schema_version,
            "busy_timeout_ms": 0,
            "journal_mode": "POSTGRES",
            "synchronous": "READ COMMITTED",
            "write_probe_ok": write_probe_ok,
            "write_probe_detail": write_probe_detail,
            "projects_total": int(projects_total),
            "archived_projects_total": int(archived_projects_total),
            "analysis_runs_total": int(analysis_runs_total),
            "export_events_total": int(export_events_total),
            "project_revisions_total": int(project_revisions_total),
            "workspace_bundle_schema_version": self.workspace_schema_version,
            "workspace_signature_enabled": self.workspace_signing_key is not None,
            "latest_project_updated_at": (
                latest_project_updated_at_row["updated_at"]
                if latest_project_updated_at_row is not None
                else None
            ),
        }

    def _run_write_probe(self) -> tuple[bool, str]:
        try:
            with self._connect() as connection:
                connection.execute("BEGIN")
                connection.execute("ROLLBACK")
            return True, "BEGIN succeeded"
        except Exception as exc:
            return False, str(exc)


def _sqlite_path_from_database_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    if parsed.scheme != "sqlite":
        return database_url
    if parsed.netloc and parsed.path:
        return unquote(f"{parsed.netloc}{parsed.path}")
    if parsed.path:
        resolved_path = unquote(parsed.path)
        if len(resolved_path) >= 4 and resolved_path[0] == "/" and resolved_path[2] == ":":
            return resolved_path[1:]
        if resolved_path.startswith("//"):
            return resolved_path[1:]
        return resolved_path
    return database_url.removeprefix("sqlite:///")


def create_backend(
    database_url: str,
    *,
    busy_timeout_ms: int = 5000,
    journal_mode: str = "WAL",
    synchronous: str = "NORMAL",
    workspace_signing_key: str | None = None,
    pool_size: int = 10,
) -> DatabaseBackend:
    parsed = urlparse(database_url)
    if parsed.scheme in {"postgres", "postgresql"}:
        return PostgresBackend(
            database_url,
            pool_size=pool_size,
            workspace_signing_key=workspace_signing_key,
        )
    return SQLiteBackend(
        _sqlite_path_from_database_url(database_url),
        busy_timeout_ms=busy_timeout_ms,
        journal_mode=journal_mode,
        synchronous=synchronous,
        workspace_signing_key=workspace_signing_key,
    )


class ProjectRepository:
    def __init__(
        self,
        database_url: str,
        *,
        busy_timeout_ms: int = 5000,
        journal_mode: str = "WAL",
        synchronous: str = "NORMAL",
        workspace_signing_key: str | None = None,
        pool_size: int = 10,
    ) -> None:
        self._backend = create_backend(
            database_url,
            busy_timeout_ms=busy_timeout_ms,
            journal_mode=journal_mode,
            synchronous=synchronous,
            workspace_signing_key=workspace_signing_key,
            pool_size=pool_size,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._backend, name)

    def set_webhook_service(self, webhook_service: Any | None) -> None:
        self._backend.set_webhook_service(webhook_service)

    def close(self) -> None:
        backend_close = getattr(self._backend, "close", None)
        if callable(backend_close):
            backend_close()
