from __future__ import annotations

import re
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Literal, cast

from jsonschema import (  # type: ignore[import-untyped]
    Draft202012Validator,
    FormatChecker,
)
from pydantic import BaseModel, ConfigDict, Field
from referencing import Registry

from app.backend.app.evidence._common import (
    SHA256_PATTERN as _SHA256_PATTERN,
)
from app.backend.app.evidence._common import (
    CanonicalJsonError,
    IJsonError,
    IJsonObjectError,
    canonical_json_bytes,
    load_ijson_object,
    sha256_hex,
)

DBT_MANIFEST_V12_SCHEMA_ID: Final = "https://schemas.getdbt.com/dbt/manifest/v12.json"
DBT_MANIFEST_V12_SCHEMA_SHA256: Final = (
    "sha256:f29ac66b0ea66b46575da0a5da66b2716f06f25295044234304e16631773ea4c"
)

DbtResourceCollection = Literal[
    "nodes",
    "sources",
    "macros",
    "docs",
    "exposures",
    "metrics",
    "groups",
    "saved_queries",
    "semantic_models",
    "unit_tests",
]
DbtOwnerSource = Literal["resource", "group"]

_SCHEMA_PATH = (
    Path(__file__).resolve().parent
    / "contracts"
    / "schemas"
    / "dbt"
    / "manifest"
    / "v12.json"
)
_RESOURCE_COLLECTIONS: tuple[DbtResourceCollection, ...] = (
    "nodes",
    "sources",
    "macros",
    "docs",
    "exposures",
    "metrics",
    "groups",
    "saved_queries",
    "semantic_models",
    "unit_tests",
)
_METRIC_SEMANTIC_FIELDS = (
    "description",
    "filter",
    "label",
    "time_granularity",
    "type",
    "type_params",
)
_MAX_MANIFEST_BYTES = 64 * 1024 * 1024
_URI_OR_DRIVE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_SENSITIVE_EXPORT_PATTERNS = (
    (
        "connection string",
        re.compile(
            r"\b(?:postgres(?:ql)?|mysql|mariadb|mssql|mongodb(?:\+srv)?|redis)://",
            re.IGNORECASE,
        ),
    ),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("cloud access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("provider token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,})\b")),
    (
        "email address",
        re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])"),
    ),
    (
        "absolute path",
        re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|/(?:Users|home|var|tmp|etc)[\\/])"),
    ),
)


class DbtManifestError(ValueError):
    """Base error for the bounded dbt manifest import boundary."""


class DbtManifestVersionError(DbtManifestError):
    """Raised when manifest schema metadata is absent or unsupported."""


class DbtManifestValidationError(DbtManifestError):
    """Raised when a manifest fails its pinned official artifact schema."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DbtResourceLineage(_FrozenModel):
    collection: DbtResourceCollection
    unique_id: str = Field(min_length=1, max_length=1024)
    name: str = Field(min_length=1, max_length=1024)
    resource_type: str = Field(min_length=1, max_length=128)
    package_name: str = Field(min_length=1, max_length=1024)
    path: str = Field(min_length=1, max_length=4096)
    digest: str = Field(pattern=_SHA256_PATTERN)


class DbtOwnerLineage(_FrozenModel):
    source: DbtOwnerSource
    owner_ref: str = Field(min_length=1, max_length=1024)
    name: str | None = Field(default=None, min_length=1, max_length=256)


class DbtMetricSemantics(_FrozenModel):
    resource: DbtResourceLineage
    dependencies: tuple[DbtResourceLineage, ...]
    definition_digest: str = Field(pattern=_SHA256_PATTERN)
    semantics_json: str = Field(min_length=2)


class DbtManifestImport(_FrozenModel):
    schema_id: Literal["https://schemas.getdbt.com/dbt/manifest/v12.json"] = (
        DBT_MANIFEST_V12_SCHEMA_ID
    )
    schema_sha256: Literal[
        "sha256:f29ac66b0ea66b46575da0a5da66b2716f06f25295044234304e16631773ea4c"
    ] = DBT_MANIFEST_V12_SCHEMA_SHA256
    dbt_version: str | None = Field(default=None, min_length=1, max_length=64)
    manifest_digest: str = Field(pattern=_SHA256_PATTERN)
    selected: DbtResourceLineage
    owner: DbtOwnerLineage | None
    dependencies: tuple[DbtResourceLineage, ...]
    metrics: tuple[DbtMetricSemantics, ...]


def _canonical_bytes(value: Any, *, label: str) -> bytes:
    try:
        return canonical_json_bytes(value)
    except CanonicalJsonError as error:
        raise DbtManifestError(f"{label} is not RFC 8785 canonicalizable") from error


def _load_json_bytes(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        return load_ijson_object(payload)
    except IJsonObjectError:
        raise DbtManifestError(f"{label} must contain a JSON object") from None
    except IJsonError as error:
        raise DbtManifestError(f"{label} is not strict UTF-8 I-JSON: {error}") from None


def _read_manifest(path: Path | str) -> bytes:
    manifest_path = Path(path)
    try:
        size = manifest_path.stat().st_size
    except OSError:
        raise DbtManifestError("dbt manifest could not be read") from None
    if size > _MAX_MANIFEST_BYTES:
        raise DbtManifestError("dbt manifest exceeds the 64 MiB import limit")
    try:
        payload = manifest_path.read_bytes()
    except OSError:
        raise DbtManifestError("dbt manifest could not be read") from None
    if len(payload) > _MAX_MANIFEST_BYTES:
        raise DbtManifestError("dbt manifest exceeds the 64 MiB import limit")
    return payload


@lru_cache(maxsize=1)
def _v12_schema() -> dict[str, Any]:
    try:
        payload = _SCHEMA_PATH.read_bytes()
    except OSError:
        raise DbtManifestError("trusted dbt manifest v12 schema is missing") from None
    if sha256_hex(payload) != DBT_MANIFEST_V12_SCHEMA_SHA256:
        raise DbtManifestError("trusted dbt manifest v12 schema digest mismatch")
    schema = _load_json_bytes(payload, label="trusted dbt manifest v12 schema")
    if schema.get("$id") != DBT_MANIFEST_V12_SCHEMA_ID:
        raise DbtManifestError("trusted dbt manifest v12 schema has the wrong identity")
    Draft202012Validator.check_schema(schema)
    return schema


def _pointer(parts: Sequence[object]) -> str:
    encoded = "/".join(
        str(part).replace("~", "~0").replace("/", "~1") for part in parts
    )
    return "/" + encoded if encoded else "/"


def _validate_v12(manifest: dict[str, Any]) -> None:
    validator = Draft202012Validator(
        _v12_schema(),
        registry=Registry(),
        format_checker=FormatChecker(),
    )
    errors = sorted(
        validator.iter_errors(manifest),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            str(error.validator),
        ),
    )
    if not errors:
        return
    details = "; ".join(
        f"{_pointer(tuple(error.absolute_path))}: {error.validator} constraint failed"
        for error in errors[:10]
    )
    if len(errors) > 10:
        details += f"; {len(errors) - 10} additional violation(s)"
    raise DbtManifestValidationError(
        f"dbt manifest does not conform to the official manifest v12 schema: {details}"
    )


def _schema_version(manifest: dict[str, Any]) -> str:
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict):
        raise DbtManifestVersionError("metadata.dbt_schema_version is required")
    schema_version = metadata.get("dbt_schema_version")
    if not isinstance(schema_version, str) or not schema_version:
        raise DbtManifestVersionError("metadata.dbt_schema_version is required")
    if schema_version != DBT_MANIFEST_V12_SCHEMA_ID:
        raise DbtManifestVersionError(f"unsupported dbt manifest schema: {schema_version}")
    return schema_version


def _safe_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise DbtManifestError("dbt resource path must be a safe relative path")
    if (
        value != value.strip()
        or value.startswith("/")
        or value.startswith("//")
        or value.startswith("~")
        or _URI_OR_DRIVE_PATTERN.match(value)
        or "\\" in value
        or "\x00" in value
        or any(ord(character) < 32 for character in value)
    ):
        raise DbtManifestError("dbt resource path must be a safe relative path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise DbtManifestError("dbt resource path must be a safe relative path")
    return value


def _required_string(resource: dict[str, Any], field: str) -> str:
    value = resource.get(field)
    if not isinstance(value, str) or not value:
        raise DbtManifestError(f"dbt resource {field} must be a non-empty string")
    return value


def _resource_lineage(
    collection: DbtResourceCollection,
    key: str,
    resource: dict[str, Any],
) -> DbtResourceLineage:
    unique_id = _required_string(resource, "unique_id")
    if unique_id != key:
        raise DbtManifestError("dbt resource key does not match unique_id")
    return DbtResourceLineage(
        collection=collection,
        unique_id=unique_id,
        name=_required_string(resource, "name"),
        resource_type=_required_string(resource, "resource_type"),
        package_name=_required_string(resource, "package_name"),
        path=_safe_relative_path(resource.get("path")),
        digest=sha256_hex(_canonical_bytes(resource, label="dbt resource")),
    )


def _resource_index(
    manifest: dict[str, Any],
) -> dict[str, tuple[DbtResourceCollection, str, dict[str, Any]]]:
    index: dict[str, tuple[DbtResourceCollection, str, dict[str, Any]]] = {}
    for collection in _RESOURCE_COLLECTIONS:
        raw_collection = manifest.get(collection)
        if not isinstance(raw_collection, dict):
            raise DbtManifestValidationError(
                "dbt manifest does not conform to the official manifest v12 schema"
            )
        for key, raw_resource in raw_collection.items():
            if not isinstance(key, str) or not isinstance(raw_resource, dict):
                raise DbtManifestValidationError(
                    "dbt manifest does not conform to the official manifest v12 schema"
                )
            resource = cast(dict[str, Any], raw_resource)
            unique_id = _required_string(resource, "unique_id")
            if unique_id != key:
                raise DbtManifestError("dbt resource key does not match unique_id")
            if unique_id in index:
                raise DbtManifestError("dbt resource unique_id is ambiguous across collections")
            index[unique_id] = (collection, key, resource)
    return index


def _locate_selected(
    index: dict[str, tuple[DbtResourceCollection, str, dict[str, Any]]],
    unique_id: str,
) -> tuple[DbtResourceCollection, str, dict[str, Any]]:
    located = index.get(unique_id)
    if located is None:
        raise DbtManifestError("selected dbt resource was not found")
    return located


def _string_items(value: object, *, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise DbtManifestError(f"{label} must contain non-empty unique IDs")
    return tuple(cast(list[str], value))


def _dependency_ids(manifest: dict[str, Any], selected_id: str, resource: dict[str, Any]) -> tuple[str, ...]:
    macro_dependencies: set[str] = set()
    node_dependencies: set[str] = set()
    depends_on = resource.get("depends_on")
    if depends_on is not None:
        if not isinstance(depends_on, dict):
            raise DbtManifestError("dbt depends_on must be an object")
        macro_dependencies.update(
            _string_items(depends_on.get("macros"), label="dbt macro dependencies")
        )
        node_dependencies.update(
            _string_items(depends_on.get("nodes"), label="dbt node dependencies")
        )

    parent_map = manifest.get("parent_map")
    if not isinstance(parent_map, dict):
        raise DbtManifestValidationError(
            "dbt manifest does not conform to the official manifest v12 schema"
        )
    parent_dependencies = set(
        _string_items(
            parent_map.get(selected_id),
            label="dbt parent_map dependencies",
        )
    )
    if node_dependencies != parent_dependencies:
        raise DbtManifestError("dbt embedded and parent_map dependency maps disagree")
    dependencies = macro_dependencies | node_dependencies
    dependencies.discard(selected_id)
    return tuple(sorted(dependencies))


def _is_descended_from(
    manifest: dict[str, Any],
    *,
    resource_id: str,
    ancestor_id: str,
) -> bool:
    if resource_id == ancestor_id:
        return True
    parent_map = manifest.get("parent_map")
    if not isinstance(parent_map, dict):
        return False
    pending = list(
        _string_items(
            parent_map.get(resource_id),
            label="dbt parent_map dependencies",
        )
    )
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current == ancestor_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(
            _string_items(
                parent_map.get(current),
                label="dbt parent_map dependencies",
            )
        )
    return False


def _owner_name(owner: dict[str, Any]) -> str | None:
    name = owner.get("name")
    if not isinstance(name, str):
        return None
    normalized = name.strip()
    if not normalized or len(normalized) > 256 or "@" in normalized:
        return None
    return normalized


def _group_name(resource: dict[str, Any]) -> str | None:
    direct = resource.get("group")
    if isinstance(direct, str) and direct:
        return direct
    config = resource.get("config")
    if isinstance(config, dict):
        configured = config.get("group")
        if isinstance(configured, str) and configured:
            return configured
    return None


def _owner_lineage(
    manifest: dict[str, Any],
    selected: DbtResourceLineage,
    resource: dict[str, Any],
) -> DbtOwnerLineage | None:
    direct_owner = resource.get("owner")
    if isinstance(direct_owner, dict):
        return DbtOwnerLineage(
            source="resource",
            owner_ref=selected.unique_id,
            name=_owner_name(cast(dict[str, Any], direct_owner)),
        )

    group_name = _group_name(resource)
    if group_name is None:
        return None
    groups = manifest.get("groups")
    if not isinstance(groups, dict):
        raise DbtManifestError("dbt resource group was not found")
    group_id = f"group.{selected.package_name}.{group_name}"
    raw_group = groups.get(group_id)
    if not isinstance(raw_group, dict):
        raise DbtManifestError("dbt resource group was not found")
    group = cast(dict[str, Any], raw_group)
    if group.get("unique_id") != group_id:
        raise DbtManifestError("dbt resource key does not match unique_id")
    raw_owner = group.get("owner")
    if not isinstance(raw_owner, dict):
        raise DbtManifestError("dbt resource group owner is missing")
    return DbtOwnerLineage(
        source="group",
        owner_ref=group_id,
        name=_owner_name(cast(dict[str, Any], raw_owner)),
    )


def _metric_semantics(
    manifest: dict[str, Any],
    metric_id: str,
    metrics: dict[str, Any],
    index: dict[str, tuple[DbtResourceCollection, str, dict[str, Any]]],
) -> DbtMetricSemantics:
    raw_metric = metrics.get(metric_id)
    if not isinstance(raw_metric, dict):
        raise DbtManifestError("dbt metric was not found")
    metric = cast(dict[str, Any], raw_metric)
    resource = _resource_lineage("metrics", metric_id, metric)
    dependencies: list[DbtResourceLineage] = []
    for dependency_id in _dependency_ids(manifest, metric_id, metric):
        located = index.get(dependency_id)
        if located is None:
            raise DbtManifestError("dbt dependency was not found")
        collection, key, dependency = located
        dependencies.append(_resource_lineage(collection, key, dependency))
    semantics = {
        field: metric[field] for field in _METRIC_SEMANTIC_FIELDS if field in metric
    }
    semantics_bytes = _canonical_bytes(
        semantics,
        label="dbt metric semantics",
    )
    return DbtMetricSemantics(
        resource=resource,
        dependencies=tuple(dependencies),
        definition_digest=sha256_hex(semantics_bytes),
        semantics_json=semantics_bytes.decode("utf-8"),
    )


def _validate_export_text(value: str) -> None:
    for label, pattern in _SENSITIVE_EXPORT_PATTERNS:
        if pattern.search(value) is not None:
            raise DbtManifestError(f"imported dbt lineage contains a {label}")


def import_dbt_manifest(
    path: Path | str,
    *,
    selected_unique_id: str,
    metric_unique_ids: Sequence[str] = (),
) -> DbtManifestImport:
    """Validate and import one explicitly selected resource from a dbt manifest."""

    if not selected_unique_id:
        raise DbtManifestError("selected_unique_id must be non-empty")
    payload = _read_manifest(path)
    manifest = _load_json_bytes(payload, label="dbt manifest")
    schema_id = _schema_version(manifest)
    _validate_v12(manifest)

    index = _resource_index(manifest)
    collection, key, selected_resource = _locate_selected(index, selected_unique_id)
    selected = _resource_lineage(collection, key, selected_resource)

    dependencies: list[DbtResourceLineage] = []
    for dependency_id in _dependency_ids(manifest, selected_unique_id, selected_resource):
        located = index.get(dependency_id)
        if located is None:
            raise DbtManifestError("dbt dependency was not found")
        dependency_collection, dependency_key, dependency_resource = located
        dependencies.append(
            _resource_lineage(
                dependency_collection,
                dependency_key,
                dependency_resource,
            )
        )

    requested_metrics: set[str] = set()
    for metric_id in metric_unique_ids:
        if not isinstance(metric_id, str) or not metric_id:
            raise DbtManifestError("metric_unique_ids must contain non-empty strings")
        requested_metrics.add(metric_id)
    if collection == "metrics":
        requested_metrics.add(selected_unique_id)
    raw_metrics = manifest.get("metrics")
    if not isinstance(raw_metrics, dict):
        raise DbtManifestValidationError(
            "dbt manifest does not conform to the official manifest v12 schema"
        )
    metric_records: list[DbtMetricSemantics] = []
    for metric_id in sorted(requested_metrics):
        if not isinstance(raw_metrics.get(metric_id), dict):
            raise DbtManifestError("dbt metric was not found")
        if not _is_descended_from(
            manifest,
            resource_id=metric_id,
            ancestor_id=selected_unique_id,
        ):
            raise DbtManifestError(
                "dbt metric is not descended from the selected dbt resource"
            )
        metric_records.append(
            _metric_semantics(manifest, metric_id, raw_metrics, index)
        )
    metrics = tuple(metric_records)

    metadata = cast(dict[str, Any], manifest["metadata"])
    dbt_version = metadata.get("dbt_version")
    if dbt_version is not None and not isinstance(dbt_version, str):
        raise DbtManifestValidationError(
            "dbt manifest does not conform to the official manifest v12 schema"
        )
    imported = DbtManifestImport(
        schema_id=cast(Literal["https://schemas.getdbt.com/dbt/manifest/v12.json"], schema_id),
        dbt_version=dbt_version,
        manifest_digest=sha256_hex(payload),
        selected=selected,
        owner=_owner_lineage(manifest, selected, selected_resource),
        dependencies=tuple(dependencies),
        metrics=metrics,
    )
    _validate_export_text(imported.model_dump_json())
    return imported
