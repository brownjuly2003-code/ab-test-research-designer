"""SQLite DDL, migrations and one-off backfills.

Split out of the backend class so the table definitions read as a schema file
rather than as private methods wedged between query methods.
"""

import json
import sqlite3
import uuid
from datetime import UTC, datetime

from app.backend.app.repository._utils import JsonParam


def create_history_tables(connection: sqlite3.Connection) -> None:
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


def create_audit_tables(connection: sqlite3.Connection) -> None:
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


def create_api_key_tables(connection: sqlite3.Connection) -> None:
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


def create_webhook_tables(connection: sqlite3.Connection) -> None:
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
            next_attempt_at TEXT,
            lease_expires_at TEXT,
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
    # idx_webhook_deliveries_due is created in migrate_db: on a legacy database the
    # next_attempt_at column does not exist until the ALTER there has run.


def create_slack_tables(connection: sqlite3.Connection) -> None:
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


def create_template_tables(connection: sqlite3.Connection) -> None:
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


def create_execution_tables(connection: sqlite3.Connection) -> None:
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


def migrate_db(connection: sqlite3.Connection) -> None:
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

    # Webhook outbox (F-09): deliveries are queued in the database and claimed by a
    # worker under a lease, so retries survive a restart. Rows that were mid-flight
    # on an old build become due immediately.
    delivery_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(webhook_deliveries)").fetchall()
    }
    for outbox_column in ("next_attempt_at", "lease_expires_at"):
        if outbox_column not in delivery_columns:
            connection.execute(f"ALTER TABLE webhook_deliveries ADD COLUMN {outbox_column} TEXT")
    connection.execute(
        """
        UPDATE webhook_deliveries
        SET next_attempt_at = COALESCE(last_attempt_at, '1970-01-01T00:00:00+00:00')
        WHERE next_attempt_at IS NULL AND status IN ('pending', 'retrying')
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_due
        ON webhook_deliveries (status, next_attempt_at)
        """
    )

    def normalize_payload_json(payload_json: object) -> JsonParam | None:
        if isinstance(payload_json, dict):
            payload = payload_json
        elif isinstance(payload_json, str):
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                return None
        else:
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
        # JsonParam so PostgreSQL JSONB columns get typed Jsonb, not a guessed string.
        return JsonParam(normalized_payload)

    create_history_tables(connection)
    create_audit_tables(connection)
    create_api_key_tables(connection)
    create_webhook_tables(connection)
    create_slack_tables(connection)
    create_template_tables(connection)
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
    backfill_analysis_runs(connection)
    backfill_project_revisions(connection)


def backfill_analysis_runs(connection: sqlite3.Connection) -> None:
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


def backfill_project_revisions(connection: sqlite3.Connection) -> None:
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
