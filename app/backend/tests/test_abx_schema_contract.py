from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_ROOT = REPO_ROOT / "app" / "backend" / "app" / "evidence" / "contracts" / "schemas" / "abx" / "0.1"
FIXTURE_ROOT = REPO_ROOT / "app" / "backend" / "tests" / "fixtures" / "abx" / "0.1"
EXPECTED_SCHEMA_FILES = {
    "amendments.schema.json",
    "common.schema.json",
    "decision-statement.schema.json",
    "decision.schema.json",
    "estimate.schema.json",
    "finding.schema.json",
    "manifest.schema.json",
    "method-profile.schema.json",
    "metric.schema.json",
    "protocol.schema.json",
    "run.schema.json",
    "source.schema.json",
}
ARTIFACT_SCHEMA_FILES = EXPECTED_SCHEMA_FILES - {"common.schema.json"}


def _reject_non_json_number(value: str) -> None:
    raise ValueError(f"non-I-JSON numeric constant: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _load_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_non_json_number,
    )


def _schema_refs(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "$ref" and isinstance(item, str):
                yield item
            else:
                yield from _schema_refs(item)
    elif isinstance(value, list):
        for item in value:
            yield from _schema_refs(item)


def _load_catalog() -> tuple[dict[str, dict[str, Any]], Registry[Any]]:
    paths = sorted(SCHEMA_ROOT.glob("*.schema.json"))
    assert {path.name for path in paths} == EXPECTED_SCHEMA_FILES

    schemas = {path.name: _load_json(path) for path in paths}
    resources: list[tuple[str, Resource[Any]]] = []
    schema_ids: set[str] = set()
    for name, schema in schemas.items():
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        schema_id = schema["$id"]
        assert schema_id.startswith("urn:evidenceos:abx:schema:0.1:")
        assert schema_id not in schema_ids, f"duplicate $id in {name}"
        Draft202012Validator.check_schema(schema)
        schema_ids.add(schema_id)
        resources.append((schema_id, Resource.from_contents(schema)))

    for name, schema in schemas.items():
        for ref in _schema_refs(schema):
            target = ref.split("#", 1)[0]
            assert not target or target in schema_ids, f"non-catalog $ref in {name}: {ref}"

    return schemas, Registry().with_resources(resources)


CASES = _load_json(FIXTURE_ROOT / "cases.json")


def _error_pointer(error: Any) -> str:
    if not error.absolute_path:
        return ""
    return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in error.absolute_path)


def test_abx_v0_1_schema_catalog_is_offline_and_meta_schema_valid() -> None:
    _load_catalog()


def test_each_artifact_schema_has_valid_and_invalid_goldens() -> None:
    verdicts: dict[str, set[bool]] = {}
    for case in CASES:
        verdicts.setdefault(case["schema"], set()).add(case["valid"])

    assert set(verdicts) == ARTIFACT_SCHEMA_FILES
    assert all(values == {False, True} for values in verdicts.values())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_abx_v0_1_golden_fixture_verdict(case: dict[str, Any]) -> None:
    schemas, registry = _load_catalog()
    fixture_path = FIXTURE_ROOT / case["fixture"]
    instance = _load_json(fixture_path)
    validator = Draft202012Validator(
        schemas[case["schema"]],
        registry=registry,
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(instance), key=lambda error: (list(error.absolute_path), error.message))

    if case["valid"]:
        assert not errors, "\n".join(error.message for error in errors)
        return

    assert errors, f"expected {fixture_path} to be schema-invalid"
    assert any(
        error.validator == case["validator"] and _error_pointer(error) == case["error_at"]
        for error in errors
    ), "\n".join(
        f"{_error_pointer(error) or '/'} [{error.validator}]: {error.message}" for error in errors
    )
