from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import rfc8785
from pydantic import ValidationError

from app.backend.app.evidence.reserved.dbt_manifest import (
    DBT_MANIFEST_V12_SCHEMA_ID,
    DBT_MANIFEST_V12_SCHEMA_SHA256,
    DbtManifestError,
    DbtManifestValidationError,
    DbtManifestVersionError,
    import_dbt_manifest,
)

METRIC_ID = "metric.analytics.conversion_rate"
SEED_ID = "seed.analytics.orders"
GROUP_ID = "group.analytics.growth"


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _manifest() -> dict[str, Any]:
    seed = {
        "database": "analytics",
        "schema": "main",
        "name": "orders",
        "resource_type": "seed",
        "package_name": "analytics",
        "path": "orders.csv",
        "original_file_path": "seeds/orders.csv",
        "unique_id": SEED_ID,
        "fqn": ["analytics", "orders"],
        "alias": "orders",
        "checksum": {"name": "sha256", "checksum": "fixture-checksum"},
        "root_path": "C:\\Users\\private\\analytics",
        "depends_on": {"macros": []},
    }
    metric = {
        "name": "conversion_rate",
        "resource_type": "metric",
        "package_name": "analytics",
        "path": "metrics.yml",
        "original_file_path": "models/metrics.yml",
        "unique_id": METRIC_ID,
        "fqn": ["analytics", "conversion_rate"],
        "description": "Completed orders divided by sessions.",
        "label": "Conversion rate",
        "type": "simple",
        "type_params": {"measure": {"name": "completed_orders"}},
        "filter": {
            "where_filters": [
                {"where_sql_template": "{{ Dimension('order__is_valid') }} = true"}
            ]
        },
        "time_granularity": "day",
        "group": "growth",
        "depends_on": {"macros": [], "nodes": [SEED_ID]},
    }
    group = {
        "name": "growth",
        "resource_type": "group",
        "package_name": "analytics",
        "path": "groups.yml",
        "original_file_path": "models/groups.yml",
        "unique_id": GROUP_ID,
        "owner": {
            "name": "Growth Analytics",
            "email": "private-owner@example.com",
        },
    }
    return {
        "metadata": {
            "dbt_schema_version": DBT_MANIFEST_V12_SCHEMA_ID,
            "dbt_version": "1.11.6",
            "generated_at": "2026-08-22T12:00:00Z",
        },
        "nodes": {SEED_ID: seed},
        "sources": {},
        "macros": {},
        "docs": {},
        "exposures": {},
        "metrics": {METRIC_ID: metric},
        "groups": {GROUP_ID: group},
        "selectors": {},
        "disabled": {},
        "parent_map": {METRIC_ID: [SEED_ID], SEED_ID: []},
        "child_map": {METRIC_ID: [], SEED_ID: [METRIC_ID]},
        "group_map": {GROUP_ID: [METRIC_ID]},
        "saved_queries": {},
        "semantic_models": {},
        "unit_tests": {},
    }


def _write_manifest(tmp_path: Path, manifest: dict[str, Any]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
        newline="\n",
    )
    return path


def test_imports_v12_selected_resource_dependencies_owner_and_metric_semantics(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    path = _write_manifest(tmp_path, manifest)

    imported = import_dbt_manifest(
        path,
        selected_unique_id=METRIC_ID,
        metric_unique_ids=(METRIC_ID,),
    )

    assert imported.schema_id == DBT_MANIFEST_V12_SCHEMA_ID
    assert imported.schema_sha256 == DBT_MANIFEST_V12_SCHEMA_SHA256
    assert imported.dbt_version == "1.11.6"
    assert imported.manifest_digest == _sha256(path.read_bytes())

    assert imported.selected.collection == "metrics"
    assert imported.selected.unique_id == METRIC_ID
    assert imported.selected.resource_type == "metric"
    assert imported.selected.package_name == "analytics"
    assert imported.selected.path == "metrics.yml"
    assert imported.selected.digest == _sha256(rfc8785.dumps(manifest["metrics"][METRIC_ID]))

    assert imported.owner is not None
    assert imported.owner.source == "group"
    assert imported.owner.owner_ref == GROUP_ID
    assert imported.owner.name == "Growth Analytics"

    assert len(imported.dependencies) == 1
    dependency = imported.dependencies[0]
    assert dependency.collection == "nodes"
    assert dependency.unique_id == SEED_ID
    assert dependency.resource_type == "seed"
    assert dependency.path == "orders.csv"
    assert dependency.digest == _sha256(rfc8785.dumps(manifest["nodes"][SEED_ID]))

    assert len(imported.metrics) == 1
    metric = imported.metrics[0]
    assert metric.resource.unique_id == METRIC_ID
    assert tuple(item.unique_id for item in metric.dependencies) == (SEED_ID,)
    expected_semantics = {
        "description": "Completed orders divided by sessions.",
        "filter": {
            "where_filters": [
                {"where_sql_template": "{{ Dimension('order__is_valid') }} = true"}
            ]
        },
        "label": "Conversion rate",
        "time_granularity": "day",
        "type": "simple",
        "type_params": {"measure": {"name": "completed_orders"}},
    }
    assert json.loads(metric.semantics_json) == expected_semantics
    assert metric.definition_digest == _sha256(rfc8785.dumps(expected_semantics))
    assert metric.definition_digest != metric.resource.digest

    serialized = imported.model_dump_json()
    assert "root_path" not in serialized
    assert "C:\\\\Users\\\\private" not in serialized
    assert "private-owner@example.com" not in serialized
    assert str(path) not in serialized

    with pytest.raises(ValidationError, match="frozen"):
        imported.selected.path = "changed.yml"


def test_selected_seed_omits_schema_valid_absolute_root_path(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _manifest())

    imported = import_dbt_manifest(
        path,
        selected_unique_id=SEED_ID,
        metric_unique_ids=(METRIC_ID,),
    )

    assert imported.selected.path == "orders.csv"
    assert "root_path" not in imported.model_dump_json()
    assert "C:\\\\Users\\\\private" not in imported.model_dump_json()


@pytest.mark.parametrize(
    "schema_version, message",
    [
        (None, "metadata.dbt_schema_version is required"),
        ("https://schemas.getdbt.com/dbt/manifest/v11.json", "unsupported dbt manifest schema"),
    ],
)
def test_requires_explicit_supported_schema_version(
    tmp_path: Path,
    schema_version: str | None,
    message: str,
) -> None:
    manifest = _manifest()
    if schema_version is None:
        manifest["metadata"].pop("dbt_schema_version")
    else:
        manifest["metadata"]["dbt_schema_version"] = schema_version
    path = _write_manifest(tmp_path, manifest)

    with pytest.raises(DbtManifestVersionError, match=message):
        import_dbt_manifest(path, selected_unique_id=METRIC_ID)


def test_validates_complete_manifest_against_official_v12_schema(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest.pop("semantic_models")
    path = _write_manifest(tmp_path, manifest)

    with pytest.raises(DbtManifestValidationError, match="official manifest v12 schema"):
        import_dbt_manifest(path, selected_unique_id=METRIC_ID)


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "C:\\private\\metrics.yml",
        "../metrics.yml",
        "/tmp/metrics.yml",
        "file:/tmp/metrics.yml",
        "~/private/metrics.yml",
        " metrics/private.yml",
    ],
)
def test_rejects_unsafe_selected_resource_paths(tmp_path: Path, unsafe_path: str) -> None:
    manifest = _manifest()
    manifest["metrics"][METRIC_ID]["path"] = unsafe_path
    path = _write_manifest(tmp_path, manifest)

    with pytest.raises(DbtManifestError, match="safe relative path"):
        import_dbt_manifest(path, selected_unique_id=METRIC_ID)


def test_rejects_unknown_or_mismatched_resource_identity(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _manifest())

    with pytest.raises(DbtManifestError, match="selected dbt resource was not found"):
        import_dbt_manifest(path, selected_unique_id="metric.analytics.missing")

    manifest = _manifest()
    manifest["metrics"][METRIC_ID]["unique_id"] = "metric.analytics.different"
    path = _write_manifest(tmp_path, manifest)
    with pytest.raises(DbtManifestError, match="resource key does not match unique_id"):
        import_dbt_manifest(path, selected_unique_id=METRIC_ID)


def test_rejects_unknown_metric_and_dependency_lineage(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _manifest())
    with pytest.raises(DbtManifestError, match="dbt metric was not found"):
        import_dbt_manifest(
            path,
            selected_unique_id=METRIC_ID,
            metric_unique_ids=("metric.analytics.missing",),
        )

    manifest = _manifest()
    manifest["metrics"][METRIC_ID]["depends_on"]["nodes"] = ["model.analytics.missing"]
    manifest["parent_map"][METRIC_ID] = ["model.analytics.missing"]
    path = _write_manifest(tmp_path, manifest)
    with pytest.raises(DbtManifestError, match="dbt dependency was not found"):
        import_dbt_manifest(path, selected_unique_id=METRIC_ID)


def test_requires_embedded_and_parent_map_dependencies_to_agree(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["parent_map"][METRIC_ID] = []
    path = _write_manifest(tmp_path, manifest)

    with pytest.raises(DbtManifestError, match="dependency maps disagree"):
        import_dbt_manifest(path, selected_unique_id=METRIC_ID)


def test_rejects_metric_outside_selected_resource_ancestry(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["metrics"][METRIC_ID]["depends_on"]["nodes"] = []
    manifest["parent_map"][METRIC_ID] = []
    path = _write_manifest(tmp_path, manifest)

    with pytest.raises(DbtManifestError, match="not descended from the selected dbt resource"):
        import_dbt_manifest(
            path,
            selected_unique_id=SEED_ID,
            metric_unique_ids=(METRIC_ID,),
        )


def test_hashes_separate_manifest_resource_and_metric_semantics(tmp_path: Path) -> None:
    manifest = _manifest()
    path = _write_manifest(tmp_path, manifest)
    baseline = import_dbt_manifest(
        path,
        selected_unique_id=SEED_ID,
        metric_unique_ids=(METRIC_ID,),
    )

    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")
    reformatted = import_dbt_manifest(
        path,
        selected_unique_id=SEED_ID,
        metric_unique_ids=(METRIC_ID,),
    )
    assert reformatted.manifest_digest != baseline.manifest_digest
    assert reformatted.selected.digest == baseline.selected.digest
    assert reformatted.metrics[0].definition_digest == baseline.metrics[0].definition_digest

    manifest["metrics"][METRIC_ID]["description"] = "Changed semantics."
    path = _write_manifest(tmp_path, manifest)
    changed_metric = import_dbt_manifest(
        path,
        selected_unique_id=SEED_ID,
        metric_unique_ids=(METRIC_ID,),
    )
    assert changed_metric.selected.digest == baseline.selected.digest
    assert changed_metric.metrics[0].definition_digest != baseline.metrics[0].definition_digest


def test_rejects_duplicate_json_keys_before_schema_validation(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        '{"metadata":{"dbt_schema_version":"'
        + DBT_MANIFEST_V12_SCHEMA_ID
        + '","dbt_schema_version":"'
        + DBT_MANIFEST_V12_SCHEMA_ID
        + '"}}',
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(DbtManifestError, match="duplicate JSON key"):
        import_dbt_manifest(path, selected_unique_id=METRIC_ID)


def test_rejects_non_unicode_scalar_ijson_strings(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["metadata"]["invocation_id"] = "\ud800"
    path = tmp_path / "manifest.json"
    path.write_bytes(json.dumps(manifest, ensure_ascii=True).encode("utf-8"))

    with pytest.raises(DbtManifestError, match="Unicode scalar"):
        import_dbt_manifest(path, selected_unique_id=METRIC_ID)


def test_rejects_email_leakage_from_projected_metric_semantics(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["metrics"][METRIC_ID]["description"] = (
        "Contact private-metric-owner@example.com for the definition."
    )
    path = _write_manifest(tmp_path, manifest)

    with pytest.raises(DbtManifestError, match="email address"):
        import_dbt_manifest(path, selected_unique_id=METRIC_ID)
