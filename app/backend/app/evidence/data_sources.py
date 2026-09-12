from __future__ import annotations

import hashlib
import math
import re
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Literal, Protocol, TypeVar, cast, runtime_checkable
from uuid import UUID

import duckdb
import psycopg
from psycopg import IsolationLevel, sql
from pydantic import BaseModel, ConfigDict, Field

from app.backend.app.evidence._common import SHA256_PATTERN as _SHA256_PATTERN
from app.backend.app.evidence.query_identity import (
    digest_json,
    query_identity_digest,
    sha256_prefixed,
)

QueryDialect = Literal["duckdb", "postgresql"]
FingerprintMethod = Literal["content_sha256", "transaction_snapshot"]
FingerprintStrength = Literal["strong", "bounded", "weak"]
QueryValue = str | int | float | bool | None
_T = TypeVar("_T")
_RUNNER_VERSION = "0.1.0"
_SOURCE_REF_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_RELATION_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}(?:\.[A-Za-z_][A-Za-z0-9_]{0,62})?$")
_READ_QUERY_PATTERN = re.compile(r"^(?:SELECT|WITH)\b", re.IGNORECASE)


class DataSourceError(RuntimeError):
    """Base error for the bounded evidence data-source boundary."""


class DataSourcePolicyError(DataSourceError):
    """Raised before execution when a query exceeds the adapter's authority."""


class DataSourceConnectionError(DataSourceError):
    """Raised without serializing a connection string or local source path."""


class QueryBudgetExceededError(DataSourceError):
    """Raised when the declared scan or result budget would be exceeded."""


class QueryTimeoutError(DataSourceError):
    """Raised when the engine interrupts a query at its declared deadline."""


class QueryCancelledError(DataSourceError):
    """Raised when a caller explicitly cancels the adapter's active operation."""


class QueryExecutionError(DataSourceError):
    """Raised with a redacted engine-level execution failure."""


class DataSourceBusyError(DataSourceError):
    """Raised when one adapter instance already owns an active connection."""


class QueryBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_scan_rows: int = Field(ge=1, le=1_000_000_000_000)
    timeout_ms: int = Field(ge=1, le=300_000)
    max_result_rows: int = Field(ge=1, le=10_000)


class AggregateQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    statement: str = Field(min_length=1, max_length=100_000)
    parameters: tuple[QueryValue, ...] = ()
    budget: QueryBudget


class SourceColumn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    data_type: str = Field(min_length=1, max_length=256)
    nullable: bool | None = None


class SourceFingerprint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    method: FingerprintMethod
    value: str = Field(min_length=1, max_length=512)
    strength: FingerprintStrength


class EngineIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: QueryDialect
    version: str = Field(min_length=1, max_length=64)


class SourceInspection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_ref: str = Field(pattern=_SOURCE_REF_PATTERN.pattern)
    relation: str = Field(min_length=1, max_length=128)
    engine: EngineIdentity
    fingerprint: SourceFingerprint
    columns: tuple[SourceColumn, ...]
    estimated_rows: int = Field(ge=0)
    schema_digest: str = Field(pattern=_SHA256_PATTERN)


class QueryValidation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    estimated_scan_rows: int = Field(ge=0)


class QueryProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query_id: str = Field(pattern=_SHA256_PATTERN)
    source_ref: str = Field(pattern=_SOURCE_REF_PATTERN.pattern)
    source_fingerprint: SourceFingerprint
    dialect: QueryDialect
    statement: str = Field(min_length=1, max_length=100_000)
    statement_digest: str = Field(pattern=_SHA256_PATTERN)
    parameters_digest: str = Field(pattern=_SHA256_PATTERN)
    engine: EngineIdentity
    runner_name: Literal["trialmark-data-source-adapter"] = "trialmark-data-source-adapter"
    runner_version: str = _RUNNER_VERSION
    estimated_scan_rows: int = Field(ge=0)


class AggregateResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    columns: tuple[str, ...]
    rows: tuple[tuple[QueryValue, ...], ...]
    provenance: QueryProvenance


@runtime_checkable
class DataSourceAdapter(Protocol):
    @property
    def dialect(self) -> QueryDialect: ...

    def introspect(self) -> SourceInspection: ...

    def fingerprint(self) -> SourceFingerprint: ...

    def validate(self, query: AggregateQuery) -> QueryValidation: ...

    def execute(self, query: AggregateQuery) -> AggregateResult: ...

    def cancel(self) -> None: ...


def _canonical_statement(statement: str) -> str:
    normalized = statement.strip()
    if normalized.endswith(";"):
        normalized = normalized[:-1].rstrip()
    if ";" in normalized:
        raise DataSourcePolicyError("aggregate queries must contain a single statement")
    if "--" in normalized or "/*" in normalized:
        raise DataSourcePolicyError("SQL comments are outside the reviewable query contract")
    if not _READ_QUERY_PATTERN.match(normalized):
        raise DataSourcePolicyError("aggregate queries must start with SELECT or WITH")
    return normalized


def _validated_source_ref(source_ref: str) -> str:
    if not _SOURCE_REF_PATTERN.fullmatch(source_ref):
        raise ValueError("source_ref must be an opaque identifier, not a path or connection string")
    return source_ref


def _validated_relation(relation: str, *, allow_schema: bool) -> str:
    if not _RELATION_PATTERN.fullmatch(relation):
        raise ValueError("relation must contain one or two unquoted SQL identifiers")
    if not allow_schema and "." in relation:
        raise ValueError("DuckDB file relations cannot be schema-qualified")
    return relation


def _quoted_identifier(relation: str) -> str:
    return ".".join(f'"{part}"' for part in relation.split("."))


def _portable_value(value: object) -> QueryValue:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise QueryExecutionError("query returned a non-finite numeric value")
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime, time, UUID)):
        return value.isoformat() if not isinstance(value, UUID) else str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    raise QueryExecutionError(f"query returned unsupported value type: {type(value).__name__}")


def _portable_rows(rows: Sequence[Sequence[object]]) -> tuple[tuple[QueryValue, ...], ...]:
    return tuple(tuple(_portable_value(value) for value in row) for row in rows)


def _schema_digest(columns: Sequence[SourceColumn]) -> str:
    return digest_json([column.model_dump(mode="json") for column in columns])


def _provenance(
    *,
    query: AggregateQuery,
    statement: str,
    validation: QueryValidation,
    source_ref: str,
    fingerprint: SourceFingerprint,
    engine: EngineIdentity,
) -> QueryProvenance:
    statement_digest = sha256_prefixed(statement.encode("utf-8"))
    parameters_digest = digest_json(list(query.parameters))
    query_id = query_identity_digest(
        dialect=engine.name,
        parameters_digest=parameters_digest,
        source_fingerprint=fingerprint.model_dump(mode="json"),
        statement_digest=statement_digest,
    )
    return QueryProvenance(
        query_id=query_id,
        source_ref=source_ref,
        source_fingerprint=fingerprint,
        dialect=engine.name,
        statement=statement,
        statement_digest=statement_digest,
        parameters_digest=parameters_digest,
        engine=engine,
        estimated_scan_rows=validation.estimated_scan_rows,
    )


_INTERRUPT_RETRY_SECONDS: Final = 0.05
_WATCHDOG_JOIN_SECONDS: Final = 5.0


class DuckDbFileAdapter:
    """A hardened, one-file DuckDB aggregate-query boundary."""

    def __init__(
        self,
        *,
        path: Path | str,
        relation: str,
        source_ref: str,
        metadata_timeout_ms: int = 30_000,
    ) -> None:
        source_path = Path(path).resolve(strict=True)
        if not source_path.is_file():
            raise ValueError("DuckDB source path must name one file")
        if source_path.suffix.lower() not in {".csv", ".parquet"}:
            raise ValueError("DuckDB file adapter accepts only CSV or Parquet")
        if metadata_timeout_ms < 1 or metadata_timeout_ms > 300_000:
            raise ValueError("metadata_timeout_ms must be between 1 and 300000")
        self._path = source_path
        self._relation = _validated_relation(relation, allow_schema=False)
        self._source_ref = _validated_source_ref(source_ref)
        self._metadata_timeout_ms = metadata_timeout_ms
        self._active_lock = threading.Lock()
        self._active_connection: duckdb.DuckDBPyConnection | None = None
        self._cancel_requested = threading.Event()

    @property
    def dialect(self) -> QueryDialect:
        return "duckdb"

    def _connect(self) -> duckdb.DuckDBPyConnection:
        connection: duckdb.DuckDBPyConnection | None = None
        try:
            connection = duckdb.connect(
                ":memory:",
                config={
                    "threads": "1",
                    "memory_limit": "256MB",
                    "max_temp_directory_size": "0B",
                    "autoinstall_known_extensions": "false",
                    "autoload_known_extensions": "false",
                    "allow_community_extensions": "false",
                    "allow_persistent_secrets": "false",
                },
            )
            connection.execute("SET allowed_paths = ?", [[str(self._path)]])
            connection.execute("SET enable_external_access = false")
            return connection
        except duckdb.Error:
            if connection is not None:
                connection.close()
            raise DataSourceConnectionError(f"could not initialize DuckDB source {self._source_ref}") from None

    def _prepare(self, connection: duckdb.DuckDBPyConnection) -> None:
        try:
            if self._path.suffix.lower() == ".parquet":
                relation = connection.read_parquet(str(self._path))
            else:
                relation = connection.read_csv(str(self._path))
            relation.create_view(self._relation, replace=True)
            connection.execute("SET lock_configuration = true")
        except duckdb.InterruptException:
            raise
        except duckdb.Error:
            raise QueryExecutionError(f"could not open DuckDB source {self._source_ref}") from None

    def _activate(self, connection: duckdb.DuckDBPyConnection) -> None:
        with self._active_lock:
            if self._active_connection is not None:
                raise DataSourceBusyError("this DuckDB adapter already has an active operation")
            self._cancel_requested.clear()
            self._active_connection = connection

    def _deactivate(self, connection: duckdb.DuckDBPyConnection) -> None:
        with self._active_lock:
            if self._active_connection is connection:
                self._active_connection = None

    def _run_bounded(
        self,
        connection: duckdb.DuckDBPyConnection,
        *,
        timeout_ms: int,
        operation: Callable[[], _T],
    ) -> _T:
        timeout_triggered = threading.Event()
        finished = threading.Event()

        def interrupt_at_deadline() -> None:
            """Ask, and keep asking, until the operation returns.

            DuckDB clears the interrupt flag when a query starts, so an
            interrupt delivered in the window between arming this watchdog and
            execution actually beginning is simply lost -- and at a
            single-digit millisecond budget that window is most of the wait. A
            single-shot timer therefore enforced the deadline only when it
            happened to win the race; when it lost, the query ran with no bound
            at all. That is the whole point of the timeout, so the watchdog
            retries rather than firing once.
            """

            if finished.wait(timeout_ms / 1000):
                return
            timeout_triggered.set()
            while not finished.is_set():
                connection.interrupt()
                finished.wait(_INTERRUPT_RETRY_SECONDS)

        self._activate(connection)
        watchdog = threading.Thread(
            target=interrupt_at_deadline,
            name="duckdb-query-deadline",
            daemon=True,
        )
        watchdog.start()
        try:
            return operation()
        except duckdb.InterruptException:
            if timeout_triggered.is_set():
                raise QueryTimeoutError("DuckDB query timed out") from None
            raise QueryCancelledError("DuckDB query was cancelled") from None
        except duckdb.Error:
            raise QueryExecutionError("DuckDB query failed") from None
        finally:
            finished.set()
            # Callers close the connection the moment this returns, so the
            # watchdog has to be off it before that happens.
            watchdog.join(timeout=_WATCHDOG_JOIN_SECONDS)
            self._deactivate(connection)

    def _fingerprint_file(self) -> SourceFingerprint:
        digest = hashlib.sha256()
        try:
            with self._path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
        except OSError:
            raise DataSourceConnectionError(f"could not read DuckDB source {self._source_ref}") from None
        return SourceFingerprint(
            method="content_sha256",
            value=f"sha256:{digest.hexdigest()}",
            strength="strong",
        )

    def fingerprint(self) -> SourceFingerprint:
        return self._fingerprint_file()

    def _estimated_rows(self, connection: duckdb.DuckDBPyConnection) -> int:
        row = connection.execute(f"SELECT COUNT(*) FROM {_quoted_identifier(self._relation)}").fetchone()
        if row is None:
            raise QueryExecutionError("DuckDB source row estimate was unavailable")
        return int(row[0])

    def _inspection(
        self,
        connection: duckdb.DuckDBPyConnection,
        fingerprint: SourceFingerprint,
    ) -> SourceInspection:
        description = connection.execute(
            f"DESCRIBE SELECT * FROM {_quoted_identifier(self._relation)}"
        ).fetchall()
        columns = tuple(
            SourceColumn(
                name=str(row[0]),
                data_type=str(row[1]),
                nullable=str(row[2]).upper() == "YES",
            )
            for row in description
        )
        return SourceInspection(
            source_ref=self._source_ref,
            relation=self._relation,
            engine=EngineIdentity(name="duckdb", version=duckdb.__version__),
            fingerprint=fingerprint,
            columns=columns,
            estimated_rows=self._estimated_rows(connection),
            schema_digest=_schema_digest(columns),
        )

    def introspect(self) -> SourceInspection:
        fingerprint = self._fingerprint_file()
        connection = self._connect()
        try:
            inspection = self._run_bounded(
                connection,
                timeout_ms=self._metadata_timeout_ms,
                operation=lambda: self._prepare_and_inspect(connection, fingerprint),
            )
        finally:
            connection.close()
        if self._fingerprint_file() != fingerprint:
            raise QueryExecutionError("DuckDB source changed during introspection")
        return inspection

    def _prepare_and_inspect(
        self,
        connection: duckdb.DuckDBPyConnection,
        fingerprint: SourceFingerprint,
    ) -> SourceInspection:
        self._prepare(connection)
        return self._inspection(connection, fingerprint)

    def _query_dependencies(
        self,
        connection: duckdb.DuckDBPyConnection,
        statement: str,
    ) -> set[str]:
        try:
            statements = connection.extract_statements(statement)
            table_names = connection.get_table_names(statement)
        except duckdb.InterruptException:
            raise
        except duckdb.Error:
            raise DataSourcePolicyError("query must read the configured relation") from None
        if len(statements) != 1:
            raise DataSourcePolicyError("aggregate queries must contain a single statement")
        if statements[0].type.name != "SELECT":
            raise DataSourcePolicyError("DuckDB aggregate queries must be SELECT statements")
        if self._relation not in table_names:
            raise DataSourcePolicyError("query must read the configured relation")
        unrelated = table_names - {self._relation}
        if unrelated:
            raise DataSourcePolicyError("query may not read unrelated relations")
        return table_names

    def _validation(
        self,
        connection: duckdb.DuckDBPyConnection,
        query: AggregateQuery,
    ) -> QueryValidation:
        estimated_rows = self._estimated_rows(connection)
        if estimated_rows > query.budget.max_scan_rows:
            raise QueryBudgetExceededError(
                f"estimated {estimated_rows} rows exceed the scan-row budget of {query.budget.max_scan_rows}"
            )
        return QueryValidation(estimated_scan_rows=estimated_rows)

    def validate(self, query: AggregateQuery) -> QueryValidation:
        statement = _canonical_statement(query.statement)
        connection = self._connect()
        try:
            return self._run_bounded(
                connection,
                timeout_ms=query.budget.timeout_ms,
                operation=lambda: self._prepare_and_validate(connection, query, statement),
            )
        finally:
            connection.close()

    def _prepare_and_validate(
        self,
        connection: duckdb.DuckDBPyConnection,
        query: AggregateQuery,
        statement: str,
    ) -> QueryValidation:
        self._query_dependencies(connection, statement)
        self._prepare(connection)
        return self._validation(connection, query)

    def execute(self, query: AggregateQuery) -> AggregateResult:
        statement = _canonical_statement(query.statement)
        fingerprint = self._fingerprint_file()
        connection = self._connect()
        try:
            validation, columns, rows = self._run_bounded(
                connection,
                timeout_ms=query.budget.timeout_ms,
                operation=lambda: self._execute(connection, query, statement),
            )
        finally:
            connection.close()
        if self._fingerprint_file() != fingerprint:
            raise QueryExecutionError("DuckDB source changed during query execution")
        engine = EngineIdentity(name="duckdb", version=duckdb.__version__)
        return AggregateResult(
            columns=columns,
            rows=rows,
            provenance=_provenance(
                query=query,
                statement=statement,
                validation=validation,
                source_ref=self._source_ref,
                fingerprint=fingerprint,
                engine=engine,
            ),
        )

    def _execute(
        self,
        connection: duckdb.DuckDBPyConnection,
        query: AggregateQuery,
        statement: str,
    ) -> tuple[QueryValidation, tuple[str, ...], tuple[tuple[QueryValue, ...], ...]]:
        self._query_dependencies(connection, statement)
        self._prepare(connection)
        validation = self._validation(connection, query)
        cursor = connection.execute(statement, list(query.parameters))
        if cursor.description is None:
            raise QueryExecutionError("DuckDB aggregate query returned no result set")
        columns = tuple(str(column[0]) for column in cursor.description)
        rows = cursor.fetchmany(query.budget.max_result_rows + 1)
        if len(rows) > query.budget.max_result_rows:
            raise QueryBudgetExceededError(
                f"query exceeded the result-row budget of {query.budget.max_result_rows}"
            )
        return validation, columns, _portable_rows(rows)

    def cancel(self) -> None:
        with self._active_lock:
            connection = self._active_connection
            if connection is not None:
                self._cancel_requested.set()
                connection.interrupt()


class PostgreSqlAdapter:
    """A PostgreSQL aggregate adapter enforced by a rollback-only read-only transaction."""

    def __init__(
        self,
        *,
        dsn: str,
        relation: str,
        source_ref: str,
        metadata_timeout_ms: int = 30_000,
        connect_timeout_seconds: int = 10,
    ) -> None:
        if not dsn.strip():
            raise ValueError("dsn must not be blank")
        if metadata_timeout_ms < 1 or metadata_timeout_ms > 300_000:
            raise ValueError("metadata_timeout_ms must be between 1 and 300000")
        if connect_timeout_seconds < 1 or connect_timeout_seconds > 60:
            raise ValueError("connect_timeout_seconds must be between 1 and 60")
        self._dsn = dsn
        self._relation = _validated_relation(relation, allow_schema=True)
        self._source_ref = _validated_source_ref(source_ref)
        self._metadata_timeout_ms = metadata_timeout_ms
        self._connect_timeout_seconds = connect_timeout_seconds
        self._active_lock = threading.Lock()
        self._active_connection: psycopg.Connection[tuple[Any, ...]] | None = None
        self._cancel_requested = threading.Event()

    @property
    def dialect(self) -> QueryDialect:
        return "postgresql"

    def _connect(self) -> psycopg.Connection[tuple[Any, ...]]:
        try:
            connection = psycopg.connect(
                self._dsn,
                connect_timeout=self._connect_timeout_seconds,
            )
        except psycopg.Error:
            raise DataSourceConnectionError(f"could not connect to PostgreSQL source {self._source_ref}") from None
        return connection

    def _activate(self, connection: psycopg.Connection[tuple[Any, ...]]) -> None:
        with self._active_lock:
            if self._active_connection is not None:
                raise DataSourceBusyError("this PostgreSQL adapter already has an active operation")
            self._cancel_requested.clear()
            self._active_connection = connection

    def _deactivate(self, connection: psycopg.Connection[tuple[Any, ...]]) -> None:
        with self._active_lock:
            if self._active_connection is connection:
                self._active_connection = None

    def _run_transaction(
        self,
        *,
        timeout_ms: int,
        operation: Callable[[psycopg.Cursor[tuple[Any, ...]]], _T],
    ) -> _T:
        connection = self._connect()
        self._activate(connection)
        try:
            connection.read_only = True
            connection.isolation_level = IsolationLevel.REPEATABLE_READ
            with connection.transaction(force_rollback=True):
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('statement_timeout', %s, true)",
                        (f"{timeout_ms}ms",),
                    )
                    return operation(cursor)
        except psycopg.errors.QueryCanceled:
            if self._cancel_requested.is_set():
                raise QueryCancelledError("PostgreSQL query was cancelled") from None
            raise QueryTimeoutError("PostgreSQL query timed out") from None
        except DataSourceError:
            raise
        except psycopg.Error:
            raise QueryExecutionError("PostgreSQL query failed") from None
        finally:
            self._deactivate(connection)
            connection.close()

    def _engine(self, cursor: psycopg.Cursor[tuple[Any, ...]]) -> EngineIdentity:
        cursor.execute("SHOW server_version")
        row = cursor.fetchone()
        if row is None:
            raise QueryExecutionError("PostgreSQL server version was unavailable")
        return EngineIdentity(name="postgresql", version=str(row[0]))

    def _fingerprint(self, cursor: psycopg.Cursor[tuple[Any, ...]]) -> SourceFingerprint:
        cursor.execute("SELECT pg_current_snapshot()::text")
        row = cursor.fetchone()
        if row is None:
            raise QueryExecutionError("PostgreSQL transaction snapshot was unavailable")
        return SourceFingerprint(
            method="transaction_snapshot",
            value=str(row[0]),
            strength="strong",
        )

    def fingerprint(self) -> SourceFingerprint:
        return self._run_transaction(
            timeout_ms=self._metadata_timeout_ms,
            operation=self._fingerprint,
        )

    def _relation_identifier(self) -> sql.Composed:
        return sql.SQL(".").join(sql.Identifier(part) for part in self._relation.split("."))

    def _plan_root(self, raw_plan: object) -> Mapping[str, Any]:
        if not isinstance(raw_plan, list) or not raw_plan or not isinstance(raw_plan[0], dict):
            raise QueryExecutionError("PostgreSQL returned an invalid EXPLAIN plan")
        root = raw_plan[0].get("Plan")
        if not isinstance(root, dict):
            raise QueryExecutionError("PostgreSQL returned an invalid EXPLAIN plan")
        return cast("Mapping[str, Any]", root)

    def _estimated_scan_rows(self, plan: Mapping[str, Any]) -> int:
        children = plan.get("Plans")
        if isinstance(children, list) and children:
            return sum(
                self._estimated_scan_rows(cast("Mapping[str, Any]", child))
                for child in children
                if isinstance(child, dict)
            )
        value = plan.get("Plan Rows", 0)
        return max(0, int(value)) if isinstance(value, (int, float)) else 0

    def _plan_reads_relation(self, plan: Mapping[str, Any]) -> bool:
        parts = self._relation.split(".")
        expected_name = parts[-1]
        expected_schema = parts[0] if len(parts) == 2 else None
        if plan.get("Relation Name") == expected_name and (
            expected_schema is None or plan.get("Schema") == expected_schema
        ):
            return True
        children = plan.get("Plans")
        return isinstance(children, list) and any(
            self._plan_reads_relation(cast("Mapping[str, Any]", child))
            for child in children
            if isinstance(child, dict)
        )

    def _explain(
        self,
        cursor: psycopg.Cursor[tuple[Any, ...]],
        statement: str,
        parameters: tuple[QueryValue, ...],
    ) -> Mapping[str, Any]:
        cursor.execute(f"EXPLAIN (FORMAT JSON, VERBOSE) {statement}", parameters)
        row = cursor.fetchone()
        if row is None:
            raise QueryExecutionError("PostgreSQL EXPLAIN returned no plan")
        return self._plan_root(row[0])

    def _validation(
        self,
        cursor: psycopg.Cursor[tuple[Any, ...]],
        query: AggregateQuery,
        statement: str,
    ) -> QueryValidation:
        plan = self._explain(cursor, statement, query.parameters)
        if not self._plan_reads_relation(plan):
            raise DataSourcePolicyError("query must read the configured relation")
        estimated_rows = self._estimated_scan_rows(plan)
        if estimated_rows > query.budget.max_scan_rows:
            raise QueryBudgetExceededError(
                f"estimated {estimated_rows} rows exceed the scan-row budget of {query.budget.max_scan_rows}"
            )
        return QueryValidation(estimated_scan_rows=estimated_rows)

    def validate(self, query: AggregateQuery) -> QueryValidation:
        statement = _canonical_statement(query.statement)
        return self._run_transaction(
            timeout_ms=query.budget.timeout_ms,
            operation=lambda cursor: self._validation(cursor, query, statement),
        )

    def _inspection(self, cursor: psycopg.Cursor[tuple[Any, ...]]) -> SourceInspection:
        engine = self._engine(cursor)
        fingerprint = self._fingerprint(cursor)
        relation = self._relation_identifier()
        cursor.execute(sql.SQL("SELECT * FROM {} LIMIT 0").format(relation))
        description = tuple(cursor.description or ())
        columns: list[SourceColumn] = []
        for column in description:
            cursor.execute("SELECT format_type(%s::oid, NULL)", (column.type_code,))
            type_row = cursor.fetchone()
            data_type = str(type_row[0]) if type_row is not None else str(column.type_code)
            columns.append(
                SourceColumn(
                    name=column.name,
                    data_type=data_type,
                    nullable=None,
                )
            )
        cursor.execute(sql.SQL("EXPLAIN (FORMAT JSON, VERBOSE) SELECT * FROM {}").format(relation))
        plan_row = cursor.fetchone()
        if plan_row is None:
            raise QueryExecutionError("PostgreSQL source EXPLAIN returned no plan")
        plan = self._plan_root(plan_row[0])
        column_tuple = tuple(columns)
        return SourceInspection(
            source_ref=self._source_ref,
            relation=self._relation,
            engine=engine,
            fingerprint=fingerprint,
            columns=column_tuple,
            estimated_rows=self._estimated_scan_rows(plan),
            schema_digest=_schema_digest(column_tuple),
        )

    def introspect(self) -> SourceInspection:
        return self._run_transaction(
            timeout_ms=self._metadata_timeout_ms,
            operation=self._inspection,
        )

    def execute(self, query: AggregateQuery) -> AggregateResult:
        statement = _canonical_statement(query.statement)

        def run(cursor: psycopg.Cursor[tuple[Any, ...]]) -> AggregateResult:
            engine = self._engine(cursor)
            fingerprint = self._fingerprint(cursor)
            validation = self._validation(cursor, query, statement)
            cursor.execute(statement, query.parameters)
            if cursor.description is None:
                raise QueryExecutionError("PostgreSQL aggregate query returned no result set")
            columns = tuple(column.name for column in cursor.description)
            rows = cursor.fetchmany(query.budget.max_result_rows + 1)
            if len(rows) > query.budget.max_result_rows:
                raise QueryBudgetExceededError(
                    f"query exceeded the result-row budget of {query.budget.max_result_rows}"
                )
            return AggregateResult(
                columns=columns,
                rows=_portable_rows(rows),
                provenance=_provenance(
                    query=query,
                    statement=statement,
                    validation=validation,
                    source_ref=self._source_ref,
                    fingerprint=fingerprint,
                    engine=engine,
                ),
            )

        return self._run_transaction(timeout_ms=query.budget.timeout_ms, operation=run)

    def cancel(self) -> None:
        with self._active_lock:
            connection = self._active_connection
            if connection is not None:
                self._cancel_requested.set()
                try:
                    connection.cancel_safe(timeout=2)
                except psycopg.Error:
                    return
