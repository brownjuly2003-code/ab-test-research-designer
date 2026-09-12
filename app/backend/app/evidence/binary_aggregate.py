from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.backend.app.evidence._common import canonical_json_bytes, sha256_hex
from app.backend.app.evidence.data_sources import (
    AggregateQuery,
    DataSourceError,
    DuckDbFileAdapter,
    QueryBudget,
    QueryProvenance,
    QueryValue,
    SourceInspection,
)

_RELATION: Final = "aggregate_binary"
EXPECTED_SOURCE_SCHEMA: Final = (
    ("control_users", "BIGINT"),
    ("control_conversions", "BIGINT"),
    ("treatment_users", "BIGINT"),
    ("treatment_conversions", "BIGINT"),
)
_EXPECTED_SCHEMA: Final = EXPECTED_SOURCE_SCHEMA
_QUERY: Final = f"""
    SELECT
        control_users,
        control_conversions,
        treatment_users,
        treatment_conversions
    FROM {_RELATION}
""".strip()


class BinaryAggregateValidationError(ValueError):
    """Raised when an external aggregate source violates the pilot contract."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BinaryAggregateMetricDefinition(_FrozenModel):
    aggregation: Literal["binary_rate"]
    numerator: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    denominator: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")


class BinaryAggregateMetric(_FrozenModel):
    name: str = Field(min_length=1, max_length=256)
    direction: Literal["increase", "decrease", "neutral"]
    unit: str = Field(min_length=1, max_length=64)
    owner_ref: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
    definition: BinaryAggregateMetricDefinition


class BinaryAggregateTelemetrySchemaVersion(_FrozenModel):
    event_type: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
    version: str = Field(min_length=1, max_length=64)
    schema_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class BinaryAggregateTelemetry(_FrozenModel):
    outcome_before_exposure_count: int = Field(ge=0)
    duplicate_event_count: int = Field(ge=0)
    unlinked_subject_count: int = Field(ge=0)
    events_beyond_max_lateness_count: int = Field(ge=0)
    schema_versions: tuple[BinaryAggregateTelemetrySchemaVersion, ...] = Field(
        min_length=1
    )


class BinaryAggregateConfig(_FrozenModel):
    schema_version: Literal["1"]
    source_ref: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
    evidence_type: Literal["external_pilot"]
    partner_approved: Literal[True]
    metric: BinaryAggregateMetric
    observed_telemetry: BinaryAggregateTelemetry


class BinaryAggregateSnapshot(_FrozenModel):
    control_users: int = Field(gt=0)
    control_conversions: int = Field(ge=0)
    treatment_users: int = Field(gt=0)
    treatment_conversions: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_conversions(self) -> BinaryAggregateSnapshot:
        if self.control_conversions > self.control_users:
            raise ValueError("control conversions cannot exceed users")
        if self.treatment_conversions > self.treatment_users:
            raise ValueError("treatment conversions cannot exceed users")
        return self


class BinaryAggregateSource(_FrozenModel):
    config: BinaryAggregateConfig
    inspection: SourceInspection
    snapshot: BinaryAggregateSnapshot
    provenance: QueryProvenance


def _parse_config(value: object) -> BinaryAggregateConfig:
    try:
        return BinaryAggregateConfig.model_validate(value)
    except ValidationError:
        raise BinaryAggregateValidationError(
            "protocol trialmark.aggregate-binary extension is invalid"
        ) from None


def _describe(columns: Sequence[tuple[str, str]]) -> str:
    return ", ".join(f"{name} {data_type}" for name, data_type in columns) or "nothing"


def _validate_schema(inspection: SourceInspection) -> None:
    actual = tuple((column.name, column.data_type.upper()) for column in inspection.columns)
    if actual != _EXPECTED_SCHEMA:
        # Whoever reads this has their own CSV open in another window, so name
        # both sides. "Schema mismatch" alone sends them back to the docs.
        raise BinaryAggregateValidationError(
            "aggregate-binary source schema mismatch: expected "
            f"{_describe(_EXPECTED_SCHEMA)}; found {_describe(actual)}"
        )
    if inspection.estimated_rows != 1:
        hint = (
            " -- this looks like a row-level export; aggregate it to one row first"
            if inspection.estimated_rows > 1
            else ""
        )
        raise BinaryAggregateValidationError(
            "aggregate-binary source must contain exactly one aggregate row, found "
            f"{inspection.estimated_rows}{hint}"
        )


def _as_nonnegative_int(value: QueryValue, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BinaryAggregateValidationError(f"{field} must be an integer")
    parsed = float(value)
    if not parsed.is_integer() or parsed < 0:
        raise BinaryAggregateValidationError(f"{field} must be a non-negative integer")
    return int(parsed)


def load_binary_aggregate(path: Path | str, config_value: object) -> BinaryAggregateSource:
    """Load one partner-approved binary aggregate row through bounded DuckDB."""

    source_path = Path(path)
    if source_path.suffix.lower() != ".csv":
        raise BinaryAggregateValidationError("aggregate-binary source must be a CSV file")
    config = _parse_config(config_value)
    try:
        adapter = DuckDbFileAdapter(
            path=source_path,
            relation=_RELATION,
            source_ref=config.source_ref,
        )
        inspection = adapter.introspect()
    except (DataSourceError, ValueError) as error:
        raise BinaryAggregateValidationError(str(error)) from None
    _validate_schema(inspection)

    query = AggregateQuery(
        statement=_QUERY,
        budget=QueryBudget(max_scan_rows=1, timeout_ms=5_000, max_result_rows=1),
    )
    try:
        result = adapter.execute(query)
    except DataSourceError as error:
        raise BinaryAggregateValidationError(str(error)) from None
    if result.provenance.source_fingerprint != inspection.fingerprint:
        raise BinaryAggregateValidationError(
            "aggregate-binary source fingerprint changed after inspection"
        )
    if len(result.rows) != 1:
        raise BinaryAggregateValidationError(
            "aggregate-binary source changed after inspection"
        )
    row = result.rows[0]
    try:
        snapshot = BinaryAggregateSnapshot(
            control_users=_as_nonnegative_int(row[0], field="control_users"),
            control_conversions=_as_nonnegative_int(
                row[1], field="control_conversions"
            ),
            treatment_users=_as_nonnegative_int(row[2], field="treatment_users"),
            treatment_conversions=_as_nonnegative_int(
                row[3], field="treatment_conversions"
            ),
        )
    except ValidationError as error:
        raise BinaryAggregateValidationError(str(error)) from None
    return BinaryAggregateSource(
        config=config,
        inspection=inspection,
        snapshot=snapshot,
        provenance=result.provenance,
    )


def metric_definition_digest(config: BinaryAggregateConfig) -> str:
    """The digest a protocol's metric reference has to carry for this source.

    One implementation, so the pre-flight check and the pipeline cannot drift
    into disagreeing about whether a source matches its protocol.
    """

    definition = config.metric.definition.model_dump(mode="json")
    return sha256_hex(canonical_json_bytes(definition))


__all__ = [
    "EXPECTED_SOURCE_SCHEMA",
    "BinaryAggregateConfig",
    "BinaryAggregateSource",
    "BinaryAggregateValidationError",
    "load_binary_aggregate",
    "metric_definition_digest",
]
