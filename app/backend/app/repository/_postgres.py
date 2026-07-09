"""PostgreSQL backend.

Reuses the SQLite backend's query methods through a pooled connection that mirrors
the `sqlite3.Connection` context-manager + `execute()` surface those methods rely on.
Only the SQL dialect, the schema bootstrap and the queries that cannot be
dialect-translated are overridden.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, cast
from urllib.parse import urlparse

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.backend.app.errors import ApiError
from app.backend.app.repository._rows import (
    audit_row_to_record,
    project_list_row_to_record,
    template_row_to_record,
)
from app.backend.app.repository._sqlite import SQLiteBackend


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
        return [project_list_row_to_record(row) for row in rows]

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
            "projects": [project_list_row_to_record(row) for row in rows],
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
        return [template_row_to_record(row) for row in rows]

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
        event = audit_row_to_record(row)
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
