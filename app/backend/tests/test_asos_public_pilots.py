from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from pydantic import ValidationError

from app.backend.app.evidence.data_sources import (
    AggregateQuery,
    AggregateResult,
    DuckDbFileAdapter,
    SourceFingerprint,
)
from app.backend.app.evidence.public_pilots import (
    AsosPublicPilotValidationError,
    load_asos_public_pilot,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "evidence" / "asos"
SOURCE_SHA256 = "sha256:bdf88b27185d3f7e65912cbb421129a32ae347c2fb0d9442fe54d74266551524"
EXPECTED_FIXTURES = {
    "d53f0e": (
        184,
        46.50000000000001,
        "sha256:b190ce2e295e72e79bc77289af38d7e3d8c95373350262a5711fce5c3dc9a78b",
    ),
    "26bd38": (
        272,
        46.50000000000001,
        "sha256:f71c7a8b617ff000ce61f6fd6692a48f7632eee065dc8321bdf62ac0a54452b3",
    ),
    "834947": (
        340,
        43.50000000000001,
        "sha256:8d345cc311258bb8e6e413e99f7c80ce3c0110219f42c254c9b5cf0c4f3d9953",
    ),
}
EXPECTED_KINDS = ("binary", "count", "count", "nonnegative_real")
ASOS_COLUMNS = (
    "experiment_id",
    "variant_id",
    "metric_id",
    "time_since_start",
    "count_c",
    "count_t",
    "mean_c",
    "mean_t",
    "variance_c",
    "variance_t",
)


@pytest.mark.parametrize(("experiment_id", "expected"), EXPECTED_FIXTURES.items())
def test_loads_asos_public_benchmark_with_immutable_snapshots_and_provenance(
    experiment_id: str,
    expected: tuple[int, float, str],
) -> None:
    expected_rows, expected_latest_checkpoint, expected_fixture_sha256 = expected

    pilot = load_asos_public_pilot(
        FIXTURE_DIR / f"{experiment_id}.parquet",
        expected_experiment_id=experiment_id,
    )

    assert pilot.metadata.dataset_name == "ASOS Digital Experiments Dataset"
    assert pilot.metadata.dataset_doi == "10.17605/OSF.IO/64JSB"
    assert pilot.metadata.license == "CC-BY-4.0"
    assert pilot.metadata.experiment_id == experiment_id
    assert pilot.metadata.treatment_variant_id == 1
    assert pilot.metadata.evidence_type == "public_benchmark"
    assert pilot.metadata.partner_approved is False
    assert pilot.metadata.source_sha256 == SOURCE_SHA256
    assert pilot.inspection.estimated_rows == expected_rows
    assert tuple(column.name for column in pilot.inspection.columns) == ASOS_COLUMNS
    assert pilot.inspection.fingerprint.method == "content_sha256"
    assert pilot.inspection.fingerprint.strength == "strong"
    assert pilot.inspection.fingerprint.value == expected_fixture_sha256
    assert pilot.provenance.source_fingerprint == pilot.inspection.fingerprint
    assert pilot.provenance.source_fingerprint.strength == "strong"
    assert pilot.provenance.parameters_digest.startswith("sha256:")
    assert "?" not in pilot.provenance.statement
    assert "FROM asos_public_pilot" in pilot.provenance.statement
    assert "QUALIFY ROW_NUMBER() OVER" in pilot.provenance.statement
    assert pilot.provenance.estimated_scan_rows == expected_rows

    assert tuple(snapshot.metric_id for snapshot in pilot.snapshots) == (1, 2, 3, 4)
    assert tuple(snapshot.metric_kind for snapshot in pilot.snapshots) == EXPECTED_KINDS
    assert all(
        snapshot.time_since_start == pytest.approx(expected_latest_checkpoint)
        for snapshot in pilot.snapshots
    )
    assert all(snapshot.count_c > 0 and snapshot.count_t > 0 for snapshot in pilot.snapshots)

    with pytest.raises(ValidationError, match="frozen"):
        pilot.metadata.partner_approved = True  # type: ignore[assignment]
    with pytest.raises(ValidationError, match="frozen"):
        pilot.snapshots[0].metric_kind = "count"


def test_rejects_wrong_asos_schema(tmp_path: Path) -> None:
    malformed_path = tmp_path / "wrong-schema.parquet"
    with duckdb.connect(":memory:") as connection:
        connection.read_parquet(str(FIXTURE_DIR / "d53f0e.parquet")).project(
            ", ".join(ASOS_COLUMNS[:-1])
        ).write_parquet(str(malformed_path))

    with pytest.raises(AsosPublicPilotValidationError, match="schema mismatch"):
        load_asos_public_pilot(malformed_path, expected_experiment_id="d53f0e")


def test_rejects_wrong_expected_experiment_id() -> None:
    with pytest.raises(AsosPublicPilotValidationError, match="expected experiment_id"):
        load_asos_public_pilot(
            FIXTURE_DIR / "d53f0e.parquet",
            expected_experiment_id="ffffff",
        )


def test_rejects_multiple_treatments(tmp_path: Path) -> None:
    malformed_path = tmp_path / "multiple-treatments.parquet"
    with duckdb.connect(":memory:") as connection:
        source = connection.read_parquet(str(FIXTURE_DIR / "d53f0e.parquet"))
        source.project(
            "experiment_id, CASE WHEN metric_id = 4 THEN 2 ELSE variant_id END AS variant_id, "
            + ", ".join(ASOS_COLUMNS[2:])
        ).write_parquet(str(malformed_path))

    with pytest.raises(AsosPublicPilotValidationError, match="exactly one treatment"):
        load_asos_public_pilot(malformed_path, expected_experiment_id="d53f0e")


def test_rejects_null_aggregate_values(tmp_path: Path) -> None:
    malformed_path = tmp_path / "null-aggregate.parquet"
    with duckdb.connect(":memory:") as connection:
        source = connection.read_parquet(str(FIXTURE_DIR / "d53f0e.parquet"))
        source.project(
            "experiment_id, variant_id, metric_id, time_since_start, count_c, count_t, "
            "CASE WHEN metric_id = 1 THEN NULL ELSE mean_c END AS mean_c, "
            "mean_t, variance_c, variance_t"
        ).write_parquet(str(malformed_path))

    with pytest.raises(AsosPublicPilotValidationError, match="null aggregate"):
        load_asos_public_pilot(malformed_path, expected_experiment_id="d53f0e")


def test_rejects_incomplete_checkpoint_grid(tmp_path: Path) -> None:
    malformed_path = tmp_path / "incomplete.parquet"
    with duckdb.connect(":memory:") as connection:
        source = connection.read_parquet(str(FIXTURE_DIR / "d53f0e.parquet"))
        source.create_view("fixture_source")
        connection.sql(
            """
            SELECT *
            FROM fixture_source
            QUALIFY NOT (
                metric_id = 4
                AND ROW_NUMBER() OVER (
                    PARTITION BY metric_id
                    ORDER BY time_since_start
                ) = 1
            )
            """
        ).write_parquet(str(malformed_path))

    with pytest.raises(AsosPublicPilotValidationError, match="incomplete checkpoint grid"):
        load_asos_public_pilot(malformed_path, expected_experiment_id="d53f0e")


def test_rejects_binary_metric_mean_above_one(tmp_path: Path) -> None:
    malformed_path = tmp_path / "invalid-binary-mean.parquet"
    with duckdb.connect(":memory:") as connection:
        source = connection.read_parquet(str(FIXTURE_DIR / "d53f0e.parquet"))
        source.project(
            "experiment_id, variant_id, metric_id, time_since_start, count_c, count_t, "
            "CASE WHEN metric_id = 1 THEN 1.01 ELSE mean_c END AS mean_c, "
            "mean_t, variance_c, variance_t"
        ).write_parquet(str(malformed_path))

    with pytest.raises(AsosPublicPilotValidationError, match="metric 1 means"):
        load_asos_public_pilot(malformed_path, expected_experiment_id="d53f0e")


def test_rejects_execute_fingerprint_different_from_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_execute = DuckDbFileAdapter.execute
    changed_fingerprint = SourceFingerprint(
        method="content_sha256",
        value="sha256:" + "0" * 64,
        strength="strong",
    )

    def execute_with_changed_fingerprint(
        adapter: DuckDbFileAdapter,
        query: AggregateQuery,
    ) -> AggregateResult:
        result = original_execute(adapter, query)
        provenance = result.provenance.model_copy(
            update={"source_fingerprint": changed_fingerprint}
        )
        return result.model_copy(update={"provenance": provenance})

    monkeypatch.setattr(DuckDbFileAdapter, "execute", execute_with_changed_fingerprint)

    with pytest.raises(AsosPublicPilotValidationError, match="fingerprint changed"):
        load_asos_public_pilot(
            FIXTURE_DIR / "d53f0e.parquet",
            expected_experiment_id="d53f0e",
        )


def test_rejects_full_series_row_count_different_from_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_execute = DuckDbFileAdapter.execute

    def execute_with_missing_row(
        adapter: DuckDbFileAdapter,
        query: AggregateQuery,
    ) -> AggregateResult:
        result = original_execute(adapter, query)
        return result.model_copy(update={"rows": result.rows[:-1]})

    monkeypatch.setattr(DuckDbFileAdapter, "execute", execute_with_missing_row)

    with pytest.raises(AsosPublicPilotValidationError, match="row count changed"):
        load_asos_public_pilot(
            FIXTURE_DIR / "d53f0e.parquet",
            expected_experiment_id="d53f0e",
        )
