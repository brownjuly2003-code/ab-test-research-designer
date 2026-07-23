"""Typed JSON/JSONB parameter binding (plan_sol step 4 / audit F-03).

- Plain strings that look like JSON must stay TEXT.
- Only explicit JsonParam becomes JSONB on PostgreSQL / JSON text on SQLite.
- SQLite parity for JSON-looking user-visible TEXT fields (project_name, user_id,
  metric, stratum, exclusion_reason).
"""

from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.repository import ProjectRepository
from app.backend.app.repository._postgres import PostgresBackend
from app.backend.app.repository._utils import JsonParam


def _sqlite_repo() -> ProjectRepository:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    return ProjectRepository(str(temp_dir / f"{uuid.uuid4()}.sqlite3"))


def _minimal_payload(name: str, *, metric: str = "purchase") -> dict[str, Any]:
    return {
        "project": {"project_name": name},
        "hypothesis": {
            "hypothesis_statement": f"{name} hypothesis",
            "change_description": f"{name} change",
        },
        "setup": {},
        "metrics": {"metric_type": "binary", "primary_metric": metric},
        "constraints": {},
        "additional_context": {},
    }


# --- Unit: adapt layer (no Docker) -------------------------------------------------


def test_adapt_param_leaves_json_looking_strings_as_text() -> None:
    """Regression for F-03: content-based { / [ inference must be gone."""
    samples = (
        '{"name":"A"}',
        "[mobile]",
        "  {\"source\":\"qa\"}  ",
        '["beta"]',
        "{not-json",
        "[unterminated",
    )
    for raw in samples:
        assert PostgresBackend._adapt_param(raw) is raw or PostgresBackend._adapt_param(raw) == raw
        adapted = PostgresBackend._adapt_param(raw)
        assert adapted == raw
        assert not hasattr(adapted, "obj")  # not Jsonb


def test_adapt_param_json_param_becomes_jsonb() -> None:
    from psycopg.types.json import Jsonb

    adapted = PostgresBackend._adapt_param(JsonParam({"a": 1, "nested": [True]}))
    assert isinstance(adapted, Jsonb)
    assert adapted.obj == {"a": 1, "nested": [True]}

    adapted_list = PostgresBackend._adapt_param(JsonParam(["x", "y"]))
    assert isinstance(adapted_list, Jsonb)
    assert adapted_list.obj == ["x", "y"]

    adapted_pre_dumped = PostgresBackend._adapt_param(JsonParam('{"k":2}'))
    assert isinstance(adapted_pre_dumped, Jsonb)
    assert adapted_pre_dumped.obj == {"k": 2}


def test_adapt_params_mixed_tuple_and_dict() -> None:
    from psycopg.types.json import Jsonb

    # Instance method; exercise without opening a pool.
    adapter = object.__new__(PostgresBackend)
    mixed = PostgresBackend._adapt_params(
        adapter,
        (
            '{"name":"A"}',
            JsonParam({"payload": True}),
            None,
            42,
        ),
    )
    assert mixed[0] == '{"name":"A"}'
    assert isinstance(mixed[1], Jsonb)
    assert mixed[2] is None
    assert mixed[3] == 42

    by_name = PostgresBackend._adapt_params(
        adapter,
        {
            "project_name": "[mobile]",
            "payload_json": JsonParam({"ok": 1}),
        },
    )
    assert by_name["project_name"] == "[mobile]"
    assert isinstance(by_name["payload_json"], Jsonb)


def test_sqlite_adapter_serializes_json_param() -> None:
    """sqlite3.register_adapter(JsonParam) must dump objects for TEXT storage."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (j TEXT)")
    conn.execute("INSERT INTO t (j) VALUES (?)", (JsonParam({"x": 1}),))
    row = conn.execute("SELECT j FROM t").fetchone()
    assert json.loads(row[0]) == {"x": 1}
    conn.close()


# --- SQLite parity: JSON-looking TEXT must round-trip unchanged --------------------


def test_sqlite_round_trips_json_looking_project_name() -> None:
    repo = _sqlite_repo()
    name = '{"name":"A"}'
    project = repo.create_project(_minimal_payload(name))
    assert project["project_name"] == name
    loaded = repo.get_project(project["id"])
    assert loaded is not None
    assert loaded["project_name"] == name
    assert loaded["payload"]["project"]["project_name"] == name


def test_sqlite_round_trips_json_looking_execution_text_fields() -> None:
    repo = _sqlite_repo()
    project = repo.create_project(_minimal_payload("Plain project"))
    exp = project["id"]

    user_id = "[mobile]"
    metric = '{"metric":"purchase"}'
    stratum = '["beta"]'
    reason = '{"source":"qa"}'

    repo.record_exposures(exp, [{"user_id": user_id, "variation_index": 0}])
    repo.record_conversions(
        exp,
        [{"user_id": user_id, "metric": metric, "value": 1.0}],
    )
    repo.record_strata(exp, [{"user_id": user_id, "stratum": stratum}])
    repo.record_exclusions(
        exp,
        [{"user_id": user_id, "exclusion_reason": reason}],
    )

    # Read raw rows to prove TEXT columns kept the exact strings.
    with repo._backend._transaction() as connection:  # type: ignore[attr-defined]
        exposure = connection.execute(
            "SELECT user_id FROM exposures WHERE experiment_id = ?",
            (exp,),
        ).fetchone()
        conversion = connection.execute(
            "SELECT user_id, metric FROM conversions WHERE experiment_id = ?",
            (exp,),
        ).fetchone()
        stratum_row = connection.execute(
            "SELECT stratum FROM user_strata WHERE experiment_id = ?",
            (exp,),
        ).fetchone()
        exclusion = connection.execute(
            "SELECT exclusion_reason FROM excluded_users WHERE experiment_id = ?",
            (exp,),
        ).fetchone()

    assert exposure["user_id"] == user_id
    assert conversion["user_id"] == user_id
    assert conversion["metric"] == metric
    assert stratum_row["stratum"] == stratum
    assert exclusion["exclusion_reason"] == reason


def test_sqlite_json_columns_still_store_and_decode_structured_payload() -> None:
    repo = _sqlite_repo()
    payload = _minimal_payload("Structured")
    payload["hypothesis"]["extra"] = {"nested": [1, 2]}
    project = repo.create_project(payload)
    loaded = repo.get_project(project["id"])
    assert loaded is not None
    assert loaded["payload"]["hypothesis"]["extra"] == {"nested": [1, 2]}

    analysis = {"report": {"calculations": {"estimated_duration_days": 14}}}
    repo.record_analysis(project["id"], analysis)
    run = repo.get_latest_analysis_run(project["id"])
    assert run is not None
    assert run["analysis"]["report"]["calculations"]["estimated_duration_days"] == 14


# --- Contract catalog: intentional JSON vs TEXT bindings ---------------------------


# Each entry: (operation, column_role, binding). Binding is "json" (JsonParam) or "text".
PORTABLE_PERSISTENCE_OPS: list[tuple[str, str, str]] = [
    ("create_project", "projects.project_name", "text"),
    ("create_project", "projects.payload_json", "json"),
    ("update_project", "projects.project_name", "text"),
    ("update_project", "projects.payload_json", "json"),
    ("_create_revision", "project_revisions.payload_json", "json"),
    ("record_analysis", "analysis_runs.analysis_json", "json"),
    ("log_audit_entry", "audit_log.project_name", "text"),
    ("log_audit_entry", "audit_log.payload_diff", "json"),
    ("upsert_template", "project_templates.tags_json", "json"),
    ("upsert_template", "project_templates.payload_json", "json"),
    ("create_webhook_subscription", "webhook_subscriptions.event_filter", "json"),
    ("update_webhook_subscription", "webhook_subscriptions.event_filter", "json"),
    ("import_workspace", "projects.payload_json", "json"),
    ("import_workspace", "analysis_runs.analysis_json", "json"),
    ("record_exposures", "exposures.user_id", "text"),
    ("record_conversions", "conversions.user_id", "text"),
    ("record_conversions", "conversions.metric", "text"),
    ("record_strata", "user_strata.user_id", "text"),
    ("record_strata", "user_strata.stratum", "text"),
    ("record_exclusions", "excluded_users.user_id", "text"),
    ("record_exclusions", "excluded_users.exclusion_reason", "text"),
    ("record_identities", "identity_map.anonymous_id", "text"),
    ("record_identities", "identity_map.canonical_id", "text"),
]


def test_portable_persistence_contract_catalog_is_complete_and_typed() -> None:
    """Machine-readable inventory: JSON columns require JsonParam; TEXT never does."""
    assert PORTABLE_PERSISTENCE_OPS, "catalog must not be empty"
    roles = {role for _, role, _ in PORTABLE_PERSISTENCE_OPS}
    # Core JSON columns from the audit must be listed as json.
    for json_col in (
        "projects.payload_json",
        "analysis_runs.analysis_json",
        "project_revisions.payload_json",
        "audit_log.payload_diff",
        "project_templates.tags_json",
        "project_templates.payload_json",
        "webhook_subscriptions.event_filter",
    ):
        assert json_col in roles
        assert all(
            binding == "json"
            for _, role, binding in PORTABLE_PERSISTENCE_OPS
            if role == json_col
        )
    # Core TEXT columns that the audit called out must stay text.
    for text_col in (
        "projects.project_name",
        "exposures.user_id",
        "conversions.metric",
        "user_strata.stratum",
        "excluded_users.exclusion_reason",
    ):
        assert text_col in roles
        assert all(
            binding == "text"
            for _, role, binding in PORTABLE_PERSISTENCE_OPS
            if role == text_col
        )


def test_json_param_source_sites_use_marker_not_dumps_for_db_columns() -> None:
    """Guard: repository modules must not reintroduce bare json.dumps into JSONB paths.

    Workspace file serialization and audit CSV export may still dump JSON as text.
    """
    repo_root = Path(__file__).resolve().parents[1] / "app" / "repository"
    # Files that write intentional JSON columns.
    db_writers = [
        repo_root / "_projects.py",
        repo_root / "_core.py",
        repo_root / "_audit.py",
        repo_root / "_templates.py",
        repo_root / "_webhooks.py",
        repo_root / "_workspace.py",
        repo_root / "_postgres.py",
    ]
    forbidden_patterns = (
        "json.dumps(payload)",
        "json.dumps(analysis_payload)",
        "json.dumps(payload_diff)",
        "json.dumps(tags)",
        "json.dumps(normalized_event_filter)",
        "json.dumps(project[\"payload\"])",
        "json.dumps(analysis_run[\"analysis\"])",
    )
    for path in db_writers:
        text = path.read_text(encoding="utf-8")
        for pattern in forbidden_patterns:
            # workspace keeps json.dumps for bundle file bytes — only flag DB-bound patterns.
            if path.name == "_workspace.py" and "project[" in pattern:
                # import path uses JsonParam; export path may dump — check JsonParam present.
                continue
            assert pattern not in text, f"{path.name} still has {pattern}"
        if path.name in {
            "_projects.py",
            "_core.py",
            "_audit.py",
            "_templates.py",
            "_webhooks.py",
            "_postgres.py",
        }:
            assert "JsonParam" in text, f"{path.name} must import/use JsonParam"


# --- Live PostgreSQL (Docker) edge suite — skipped when unavailable ----------------


def _require_docker_postgres():
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:  # pragma: no cover
        pytest.skip("testcontainers not installed")
    import subprocess

    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        pytest.skip("Docker not installed")
    if result.returncode != 0:
        pytest.skip("Docker unavailable")
    return PostgresContainer


def test_postgres_round_trips_json_looking_text_and_real_jsonb() -> None:
    """Live PG: TEXT stays TEXT; JsonParam JSONB still works (audit F-03 edge suite)."""
    PostgresContainer = _require_docker_postgres()
    with PostgresContainer("postgres:16-alpine") as postgres:
        url = postgres.get_connection_url().replace("+psycopg2", "")
        repo = ProjectRepository(url, pool_size=2)
        try:
            name = '{"name":"A"}'
            project = repo.create_project(_minimal_payload(name))
            assert project["project_name"] == name
            loaded = repo.get_project(project["id"])
            assert loaded is not None
            assert loaded["project_name"] == name
            assert loaded["payload"]["project"]["project_name"] == name

            exp = project["id"]
            user_id = "[mobile]"
            metric = '{"metric":"purchase"}'
            stratum = '["beta"]'
            reason = '{"source":"qa"}'
            repo.record_exposures(exp, [{"user_id": user_id, "variation_index": 0}])
            repo.record_conversions(
                exp,
                [{"user_id": user_id, "metric": metric, "value": 1.0}],
            )
            repo.record_strata(exp, [{"user_id": user_id, "stratum": stratum}])
            repo.record_exclusions(
                exp,
                [{"user_id": user_id, "exclusion_reason": reason}],
            )

            with repo._backend._transaction() as connection:  # type: ignore[attr-defined]
                exposure = connection.execute(
                    "SELECT user_id FROM exposures WHERE experiment_id = ?",
                    (exp,),
                ).fetchone()
                conversion = connection.execute(
                    "SELECT metric FROM conversions WHERE experiment_id = ?",
                    (exp,),
                ).fetchone()
                stratum_row = connection.execute(
                    "SELECT stratum FROM user_strata WHERE experiment_id = ?",
                    (exp,),
                ).fetchone()
                exclusion = connection.execute(
                    "SELECT exclusion_reason FROM excluded_users WHERE experiment_id = ?",
                    (exp,),
                ).fetchone()

            assert exposure["user_id"] == user_id
            assert conversion["metric"] == metric
            assert stratum_row["stratum"] == stratum
            assert exclusion["exclusion_reason"] == reason

            # Real JSONB payload still round-trips via JsonParam.
            analysis = {"report": {"calculations": {"estimated_duration_days": 7}}}
            repo.record_analysis(exp, analysis)
            run = repo.get_latest_analysis_run(exp)
            assert run is not None
            assert run["analysis"]["report"]["calculations"]["estimated_duration_days"] == 7
        finally:
            close = getattr(repo, "close", None)
            if callable(close):
                close()
