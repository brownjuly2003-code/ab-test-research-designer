from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import duckdb
import psycopg
import pytest
from psycopg import sql

from app.backend.app.evidence.data_sources import (
    AggregateQuery,
    DataSourcePolicyError,
    DuckDbFileAdapter,
    PostgreSqlAdapter,
    QueryBudget,
    QueryBudgetExceededError,
    QueryExecutionError,
    QueryTimeoutError,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "evidence" / "cross_engine.csv"
POSTGRES_DSN_ENV = "AB_TEST_EVIDENCE_POSTGRES_DSN"
ABS_TOLERANCE = 1e-9


def _aggregate_statement(relation: str) -> str:
    return f"""
        SELECT
            variant,
            COUNT(*)::BIGINT AS units,
            AVG(outcome)::DOUBLE PRECISION AS mean_outcome,
            SUM(converted)::BIGINT AS conversions
        FROM {relation}
        GROUP BY variant
        ORDER BY variant
    """.strip()


def _query(statement: str, *, scan_rows: int = 100, timeout_ms: int = 500, result_rows: int = 10) -> AggregateQuery:
    return AggregateQuery(
        statement=statement,
        budget=QueryBudget(
            max_scan_rows=scan_rows,
            timeout_ms=timeout_ms,
            max_result_rows=result_rows,
        ),
    )


def test_duckdb_file_adapter_introspects_fingerprints_and_executes_csv() -> None:
    relation = "evidence_fixture"
    adapter = DuckDbFileAdapter(
        path=FIXTURE_PATH,
        relation=relation,
        source_ref="cross_engine_fixture",
    )

    inspection = adapter.introspect()
    fingerprint = adapter.fingerprint()
    statement = _aggregate_statement(relation)
    validation = adapter.validate(_query(statement))
    result = adapter.execute(_query(statement))

    assert inspection.estimated_rows == 6
    assert [column.name for column in inspection.columns] == ["unit_id", "variant", "outcome", "converted"]
    assert inspection.schema_digest.startswith("sha256:")
    assert fingerprint.method == "content_sha256"
    assert fingerprint.strength == "strong"
    assert fingerprint == inspection.fingerprint
    assert validation.estimated_scan_rows == 6
    assert result.columns == ("variant", "units", "mean_outcome", "conversions")
    assert result.rows == (
        ("control", 3, pytest.approx(10.333333333333334, abs=ABS_TOLERANCE), 1),
        ("treatment", 3, pytest.approx(13.333333333333334, abs=ABS_TOLERANCE), 2),
    )
    assert result.provenance.statement == statement
    assert result.provenance.dialect == "duckdb"
    assert result.provenance.source_ref == "cross_engine_fixture"
    assert result.provenance.source_fingerprint == fingerprint
    assert result.provenance.statement_digest.startswith("sha256:")
    assert result.provenance.parameters_digest.startswith("sha256:")
    assert result.provenance.query_id.startswith("sha256:")
    assert result.provenance.runner_version == "0.1.0"
    assert "u1" not in result.provenance.model_dump_json()


def test_duckdb_file_adapter_supports_parquet(tmp_path: Path) -> None:
    parquet_path = tmp_path / "cross_engine.parquet"
    with duckdb.connect(":memory:") as connection:
        connection.read_csv(str(FIXTURE_PATH)).write_parquet(str(parquet_path))

    adapter = DuckDbFileAdapter(
        path=parquet_path,
        relation="evidence_fixture",
        source_ref="parquet_fixture",
    )

    result = adapter.execute(_query("SELECT COUNT(*)::BIGINT AS units FROM evidence_fixture"))

    assert result.rows == ((6,),)
    assert adapter.introspect().estimated_rows == 6


def test_duckdb_file_adapter_rejects_unrelated_or_multiple_statements() -> None:
    adapter = DuckDbFileAdapter(
        path=FIXTURE_PATH,
        relation="evidence_fixture",
        source_ref="policy_fixture",
    )

    with pytest.raises(DataSourcePolicyError, match="configured relation"):
        adapter.execute(_query("SELECT * FROM read_csv_auto('C:/Windows/win.ini')"))
    with pytest.raises(DataSourcePolicyError, match="single statement"):
        adapter.execute(_query("SELECT COUNT(*) FROM evidence_fixture; SELECT 1"))


def test_duckdb_file_adapter_enforces_scan_result_and_timeout_budgets() -> None:
    adapter = DuckDbFileAdapter(
        path=FIXTURE_PATH,
        relation="evidence_fixture",
        source_ref="budget_fixture",
    )

    with pytest.raises(QueryBudgetExceededError, match="scan-row budget"):
        adapter.execute(_query("SELECT COUNT(*) FROM evidence_fixture", scan_rows=5))
    with pytest.raises(QueryBudgetExceededError, match="result-row budget"):
        adapter.execute(_query("SELECT * FROM evidence_fixture", result_rows=2))
    with pytest.raises(QueryTimeoutError, match="DuckDB query timed out"):
        adapter.execute(
            _query(
                "SELECT SUM(value) FROM evidence_fixture CROSS JOIN range(100000000000) AS generated(value)",
                timeout_ms=5,
            )
        )


def test_duckdb_timeout_survives_an_interrupt_the_engine_never_saw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deadline that arrives before the query starts must still be enforced.

    DuckDB clears the interrupt flag when a query begins, so an interrupt
    delivered a moment too early is lost. With a single-shot timer the 5 ms
    budget below then bounded nothing and the cross join ran until something
    else killed it -- on a contended CI runner, the job itself. The watchdog
    retries, so swallowing the first interrupt only delays the timeout.
    """

    adapter = DuckDbFileAdapter(
        path=FIXTURE_PATH,
        relation="evidence_fixture",
        source_ref="budget_fixture",
    )
    swallowed: list[bool] = []
    connect = DuckDbFileAdapter._connect

    class _SwallowsFirstInterrupt:
        def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
            self._connection = connection

        def interrupt(self) -> None:
            if not swallowed:
                swallowed.append(True)
                return
            self._connection.interrupt()

        def __getattr__(self, name: str) -> object:
            return getattr(self._connection, name)

    monkeypatch.setattr(
        DuckDbFileAdapter,
        "_connect",
        lambda self: _SwallowsFirstInterrupt(connect(self)),
    )

    with pytest.raises(QueryTimeoutError, match="DuckDB query timed out"):
        adapter.execute(
            _query(
                "SELECT SUM(value) FROM evidence_fixture CROSS JOIN range(100000000000) AS generated(value)",
                timeout_ms=5,
            )
        )

    assert swallowed == [True]


def test_cross_engine_fixture_matches_and_postgres_is_server_read_only() -> None:
    dsn = os.environ.get(POSTGRES_DSN_ENV)
    if not dsn:
        pytest.skip(f"{POSTGRES_DSN_ENV} is required for the real PostgreSQL gate")

    relation = f"evidence_fixture_{uuid4().hex[:12]}"
    identifier = sql.Identifier(relation)
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(
            sql.SQL(
                "CREATE TABLE {} (unit_id TEXT PRIMARY KEY, variant TEXT NOT NULL, "
                "outcome DOUBLE PRECISION NOT NULL, converted BIGINT NOT NULL)"
            ).format(identifier)
        )
        rows = [
            ("u1", "control", 10.0, 0),
            ("u2", "control", 12.5, 1),
            ("u3", "control", 8.5, 0),
            ("u4", "treatment", 13.0, 1),
            ("u5", "treatment", 15.5, 1),
            ("u6", "treatment", 11.5, 0),
        ]
        with connection.cursor() as cursor:
            cursor.executemany(
                sql.SQL("INSERT INTO {} VALUES (%s, %s, %s, %s)").format(identifier),
                rows,
            )
        connection.execute(sql.SQL("ANALYZE {}").format(identifier))

    try:
        statement = _aggregate_statement(relation)
        duckdb_adapter = DuckDbFileAdapter(
            path=FIXTURE_PATH,
            relation=relation,
            source_ref="cross_engine_fixture",
        )
        postgres_adapter = PostgreSqlAdapter(
            dsn=dsn,
            relation=relation,
            source_ref="cross_engine_fixture",
        )

        duckdb_result = duckdb_adapter.execute(_query(statement))
        postgres_result = postgres_adapter.execute(_query(statement))

        assert postgres_result.columns == duckdb_result.columns
        assert len(postgres_result.rows) == len(duckdb_result.rows)
        for postgres_row, duckdb_row in zip(postgres_result.rows, duckdb_result.rows, strict=True):
            assert postgres_row[:2] == duckdb_row[:2]
            assert float(postgres_row[2]) == pytest.approx(float(duckdb_row[2]), abs=ABS_TOLERANCE)
            assert postgres_row[3] == duckdb_row[3]
        assert postgres_result.provenance.dialect == "postgresql"
        assert postgres_result.provenance.source_fingerprint.method == "transaction_snapshot"
        assert dsn not in postgres_result.model_dump_json()

        read_only = postgres_adapter.execute(
            _query(
                "SELECT current_setting('transaction_read_only'), current_setting('statement_timeout') "
                f"FROM {relation} LIMIT 1",
                timeout_ms=125,
            )
        )
        assert read_only.rows == (("on", "125ms"),)

        mutating_cte = (
            f"WITH removed AS (DELETE FROM {relation} RETURNING unit_id) "
            "SELECT COUNT(*) FROM removed"
        )
        with pytest.raises(QueryExecutionError, match="PostgreSQL query failed"):
            postgres_adapter.execute(_query(mutating_cte))
        with psycopg.connect(dsn) as connection:
            count = connection.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(identifier)).fetchone()
        assert count == (6,)

        with pytest.raises(QueryTimeoutError, match="PostgreSQL query timed out"):
            postgres_adapter.execute(
                _query(
                    f"SELECT COUNT(*) FROM {relation}, LATERAL pg_sleep(0.5)",
                    timeout_ms=10,
                )
            )
    finally:
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP TABLE {}").format(identifier))
