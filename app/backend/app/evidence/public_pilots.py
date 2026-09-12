from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.backend.app.evidence.data_sources import (
    AggregateQuery,
    DataSourceError,
    DuckDbFileAdapter,
    QueryBudget,
    QueryProvenance,
    QueryValue,
    SourceInspection,
)

AsosMetricKind = Literal["binary", "count", "nonnegative_real"]

ASOS_DATASET_NAME: Final[Literal["ASOS Digital Experiments Dataset"]] = (
    "ASOS Digital Experiments Dataset"
)
ASOS_DATASET_DOI: Final[Literal["10.17605/OSF.IO/64JSB"]] = "10.17605/OSF.IO/64JSB"
ASOS_DATASET_URL: Final[Literal["https://osf.io/64jsb/"]] = "https://osf.io/64jsb/"
ASOS_LICENSE: Final[Literal["CC-BY-4.0"]] = "CC-BY-4.0"
ASOS_SOURCE_SHA256: Final = (
    "sha256:bdf88b27185d3f7e65912cbb421129a32ae347c2fb0d9442fe54d74266551524"
)

_EXPERIMENT_ID_PATTERN = re.compile(r"^[0-9a-f]{6}$")
_RELATION = "asos_public_pilot"
_EXPECTED_SCHEMA = (
    ("experiment_id", "VARCHAR"),
    ("variant_id", "BIGINT"),
    ("metric_id", "BIGINT"),
    ("time_since_start", "DOUBLE"),
    ("count_c", "DOUBLE"),
    ("count_t", "DOUBLE"),
    ("mean_c", "DOUBLE"),
    ("mean_t", "DOUBLE"),
    ("variance_c", "DOUBLE"),
    ("variance_t", "DOUBLE"),
)
_METRIC_KINDS: dict[int, AsosMetricKind] = {
    1: "binary",
    2: "count",
    3: "count",
    4: "nonnegative_real",
}
_FULL_SERIES_QUERY = f"""
    SELECT
        experiment_id,
        variant_id,
        metric_id,
        time_since_start,
        count_c,
        count_t,
        mean_c,
        mean_t,
        variance_c,
        variance_t
    FROM {_RELATION}
    ORDER BY metric_id, time_since_start
""".strip()
_TERMINAL_SNAPSHOT_QUERY = f"""
    SELECT
        experiment_id,
        variant_id,
        metric_id,
        time_since_start,
        count_c,
        count_t,
        mean_c,
        mean_t,
        variance_c,
        variance_t
    FROM {_RELATION}
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY metric_id
        ORDER BY time_since_start DESC
    ) = 1
    ORDER BY metric_id
""".strip()


class AsosPublicPilotValidationError(ValueError):
    """Raised when a derived public benchmark violates the frozen ASOS contract."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AsosPublicPilotMetadata(_FrozenModel):
    dataset_name: Literal["ASOS Digital Experiments Dataset"] = ASOS_DATASET_NAME
    dataset_doi: Literal["10.17605/OSF.IO/64JSB"] = ASOS_DATASET_DOI
    dataset_url: Literal["https://osf.io/64jsb/"] = ASOS_DATASET_URL
    license: Literal["CC-BY-4.0"] = ASOS_LICENSE
    source_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    experiment_id: str = Field(pattern=_EXPERIMENT_ID_PATTERN.pattern)
    treatment_variant_id: int = Field(ge=1)
    evidence_type: Literal["public_benchmark"] = "public_benchmark"
    partner_approved: Literal[False] = False


class AsosMetricSnapshot(_FrozenModel):
    metric_id: int = Field(ge=1, le=4)
    metric_kind: AsosMetricKind
    time_since_start: float = Field(gt=0)
    count_c: int = Field(gt=0)
    count_t: int = Field(gt=0)
    mean_c: float = Field(ge=0)
    mean_t: float = Field(ge=0)
    variance_c: float = Field(ge=0)
    variance_t: float = Field(ge=0)


class AsosPublicPilot(_FrozenModel):
    metadata: AsosPublicPilotMetadata
    inspection: SourceInspection
    snapshots: tuple[AsosMetricSnapshot, ...]
    provenance: QueryProvenance


def _as_text(value: QueryValue, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise AsosPublicPilotValidationError(f"{field} must be a non-empty string")
    return value


def _as_finite_float(value: QueryValue, *, field: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AsosPublicPilotValidationError(f"{field} must be numeric")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise AsosPublicPilotValidationError(f"{field} must be finite")
    if minimum is not None and parsed < minimum:
        raise AsosPublicPilotValidationError(f"{field} must be at least {minimum}")
    return parsed


def _as_positive_int(value: QueryValue, *, field: str) -> int:
    parsed = _as_finite_float(value, field=field)
    if not parsed.is_integer() or parsed <= 0:
        raise AsosPublicPilotValidationError(f"{field} must be a positive integer")
    return int(parsed)


def _validated_aggregate_values(
    row: tuple[QueryValue, ...],
    *,
    metric_id: int,
) -> tuple[float, int, int, float, float, float, float]:
    if any(value is None for value in row[4:]):
        raise AsosPublicPilotValidationError("ASOS public-pilot contains a null aggregate value")
    mean_c = _as_finite_float(row[6], field="mean_c", minimum=0.0)
    mean_t = _as_finite_float(row[7], field="mean_t", minimum=0.0)
    if metric_id == 1 and (mean_c > 1.0 or mean_t > 1.0):
        raise AsosPublicPilotValidationError("ASOS public-pilot metric 1 means must be between 0 and 1")
    return (
        _as_finite_float(row[3], field="time_since_start", minimum=0.0),
        _as_positive_int(row[4], field="count_c"),
        _as_positive_int(row[5], field="count_t"),
        mean_c,
        mean_t,
        _as_finite_float(row[8], field="variance_c", minimum=0.0),
        _as_finite_float(row[9], field="variance_t", minimum=0.0),
    )


def _validate_schema(inspection: SourceInspection) -> None:
    actual = tuple((column.name, column.data_type.upper()) for column in inspection.columns)
    if actual != _EXPECTED_SCHEMA:
        raise AsosPublicPilotValidationError("ASOS public-pilot schema mismatch")
    if inspection.estimated_rows < 1 or inspection.estimated_rows > 10_000:
        raise AsosPublicPilotValidationError("ASOS public-pilot row count is outside the fixture budget")


def load_asos_public_pilot(
    path: Path | str,
    *,
    expected_experiment_id: str,
) -> AsosPublicPilot:
    """Load one aggregate-only ASOS experiment through the bounded DuckDB adapter."""

    if _EXPERIMENT_ID_PATTERN.fullmatch(expected_experiment_id) is None:
        raise AsosPublicPilotValidationError("expected experiment_id must be six lowercase hexadecimal characters")

    try:
        adapter = DuckDbFileAdapter(
            path=path,
            relation=_RELATION,
            source_ref=f"asos_public_pilot_{expected_experiment_id}",
        )
        inspection = adapter.introspect()
    except (DataSourceError, ValueError) as error:
        raise AsosPublicPilotValidationError(str(error)) from None

    _validate_schema(inspection)
    full_series_query = AggregateQuery(
        statement=_FULL_SERIES_QUERY,
        budget=QueryBudget(
            max_scan_rows=inspection.estimated_rows,
            timeout_ms=5_000,
            max_result_rows=inspection.estimated_rows,
        ),
    )
    try:
        full_series_result = adapter.execute(full_series_query)
    except DataSourceError as error:
        raise AsosPublicPilotValidationError(str(error)) from None
    if full_series_result.provenance.source_fingerprint != inspection.fingerprint:
        raise AsosPublicPilotValidationError(
            "ASOS public-pilot source fingerprint changed after inspection"
        )
    if len(full_series_result.rows) != inspection.estimated_rows:
        raise AsosPublicPilotValidationError(
            "ASOS public-pilot row count changed after inspection"
        )

    experiment_ids: set[str] = set()
    treatment_ids: set[int] = set()
    series: dict[int, list[tuple[float, int, int, float, float, float, float]]] = {
        metric_id: [] for metric_id in _METRIC_KINDS
    }
    seen_keys: set[tuple[int, float]] = set()

    for row in full_series_result.rows:
        experiment_id = _as_text(row[0], field="experiment_id")
        variant_id = _as_positive_int(row[1], field="variant_id")
        metric_id = _as_positive_int(row[2], field="metric_id")
        if metric_id not in _METRIC_KINDS:
            raise AsosPublicPilotValidationError("ASOS public-pilot must contain metric IDs 1 through 4")
        values = _validated_aggregate_values(row, metric_id=metric_id)
        checkpoint = values[0]
        key = (metric_id, checkpoint)
        if key in seen_keys:
            raise AsosPublicPilotValidationError("ASOS public-pilot contains duplicate checkpoint keys")
        seen_keys.add(key)
        experiment_ids.add(experiment_id)
        treatment_ids.add(variant_id)
        series[metric_id].append(values)

    if experiment_ids != {expected_experiment_id}:
        raise AsosPublicPilotValidationError(
            f"fixture must contain only expected experiment_id {expected_experiment_id}"
        )
    if len(treatment_ids) != 1:
        raise AsosPublicPilotValidationError("ASOS public-pilot must contain exactly one treatment")
    if set(series) != set(_METRIC_KINDS) or any(not values for values in series.values()):
        raise AsosPublicPilotValidationError("ASOS public-pilot must contain all four metrics")

    checkpoint_grids = {tuple(value[0] for value in values) for values in series.values()}
    if len(checkpoint_grids) != 1:
        raise AsosPublicPilotValidationError("ASOS public-pilot has an incomplete checkpoint grid")

    terminal_query = AggregateQuery(
        statement=_TERMINAL_SNAPSHOT_QUERY,
        budget=QueryBudget(
            max_scan_rows=inspection.estimated_rows,
            timeout_ms=5_000,
            max_result_rows=len(_METRIC_KINDS),
        ),
    )
    try:
        terminal_result = adapter.execute(terminal_query)
    except DataSourceError as error:
        raise AsosPublicPilotValidationError(str(error)) from None
    if not (
        terminal_result.provenance.source_fingerprint
        == full_series_result.provenance.source_fingerprint
        == inspection.fingerprint
    ):
        raise AsosPublicPilotValidationError(
            "ASOS public-pilot source fingerprint changed before terminal snapshot"
        )

    terminal_series: dict[int, tuple[float, int, int, float, float, float, float]] = {}
    terminal_experiment_ids: set[str] = set()
    terminal_treatment_ids: set[int] = set()
    for row in terminal_result.rows:
        experiment_id = _as_text(row[0], field="experiment_id")
        variant_id = _as_positive_int(row[1], field="variant_id")
        metric_id = _as_positive_int(row[2], field="metric_id")
        if metric_id not in _METRIC_KINDS or metric_id in terminal_series:
            raise AsosPublicPilotValidationError(
                "ASOS public-pilot terminal snapshot must contain each metric exactly once"
            )
        terminal_experiment_ids.add(experiment_id)
        terminal_treatment_ids.add(variant_id)
        terminal_series[metric_id] = _validated_aggregate_values(row, metric_id=metric_id)

    if terminal_experiment_ids != experiment_ids or terminal_treatment_ids != treatment_ids:
        raise AsosPublicPilotValidationError("ASOS public-pilot terminal snapshot identity mismatch")
    if terminal_series != {metric_id: values[-1] for metric_id, values in series.items()}:
        raise AsosPublicPilotValidationError("ASOS public-pilot terminal snapshot mismatch")

    snapshots = tuple(
        AsosMetricSnapshot(
            metric_id=metric_id,
            metric_kind=_METRIC_KINDS[metric_id],
            time_since_start=values[0],
            count_c=values[1],
            count_t=values[2],
            mean_c=values[3],
            mean_t=values[4],
            variance_c=values[5],
            variance_t=values[6],
        )
        for metric_id, values in sorted(terminal_series.items())
    )
    terminal_checkpoints = {snapshot.time_since_start for snapshot in snapshots}
    if len(terminal_checkpoints) != 1:
        raise AsosPublicPilotValidationError("ASOS public-pilot metrics must share one terminal checkpoint")

    return AsosPublicPilot(
        metadata=AsosPublicPilotMetadata(
            source_sha256=ASOS_SOURCE_SHA256,
            experiment_id=expected_experiment_id,
            treatment_variant_id=next(iter(treatment_ids)),
        ),
        inspection=inspection,
        snapshots=snapshots,
        provenance=terminal_result.provenance,
    )
