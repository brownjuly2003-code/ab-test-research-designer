from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from app.backend.app.evidence.abx import verify_bundle
from app.backend.tests.test_evidence_abx_content_binding import (
    _ASOS_BUNDLES,
    _asos_control_bundle,
    _codes,
    _dump_json_member,
    _iter_metric_paths,
    _load_json_member,
    _load_members,
    _rebind_estimate_metric_digests,
    _rebind_manifest,
    _write_members,
)


def _assert_asos_control() -> None:
    for archive_path in _ASOS_BUNDLES:
        result = verify_bundle(archive_path)
        assert result["valid"] is True, archive_path.name
        assert result["verdicts"]["lineage"] == "pass", archive_path.name
        assert "lineage/unbound_reference" not in _codes(result), archive_path.name


@pytest.mark.parametrize(
    "extensions",
    [
        {"trialmark.aggregate-only": True},
        {"trialmark.tags": ["aggregate-only"]},
    ],
)
def test_scalar_or_array_extensions_compare_declared_digest_strings(
    tmp_path: Path,
    extensions: dict[str, Any],
) -> None:
    members = _load_members(_asos_control_bundle())
    for path in _iter_metric_paths(members):
        metric = _load_json_member(members, path)
        metric["extensions"] = extensions
        _dump_json_member(members, path, metric)
    _rebind_estimate_metric_digests(members)
    _rebind_manifest(members)

    archive_path = tmp_path / "scalar-or-array-extensions.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)

    assert result["valid"] is True
    assert result["verdicts"]["lineage"] == "pass"
    assert "lineage/unbound_reference" not in _codes(result)
    _assert_asos_control()


def test_scalar_flag_beside_embedded_definition_still_binds_definition(
    tmp_path: Path,
) -> None:
    members = _load_members(_asos_control_bundle())
    for path in _iter_metric_paths(members):
        metric = _load_json_member(members, path)
        metric["extensions"]["trialmark.aggregate-only"] = True
        _dump_json_member(members, path, metric)
    _rebind_estimate_metric_digests(members)
    _rebind_manifest(members)

    archive_path = tmp_path / "flag-beside-definition.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)

    assert result["valid"] is True
    assert result["verdicts"]["lineage"] == "pass"
    assert "lineage/unbound_reference" not in _codes(result)
    _assert_asos_control()


def test_object_extension_without_definition_key_reports_unlocated_payload(
    tmp_path: Path,
) -> None:
    members = _load_members(_asos_control_bundle())
    for path in _iter_metric_paths(members):
        metric = _load_json_member(members, path)
        asos_extension = cast(dict[str, Any], metric["extensions"]["trialmark.asos"])
        asos_extension["spec"] = asos_extension.pop("definition")
        _dump_json_member(members, path, metric)
    _rebind_estimate_metric_digests(members)
    _rebind_manifest(members)

    archive_path = tmp_path / "definition-key-renamed.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)
    messages = [
        cast(str, error["message"])
        for error in cast(list[dict[str, Any]], result["errors"])
        if error["code"] == "lineage/unbound_reference"
    ]

    assert result["valid"] is False
    assert result["verdicts"]["lineage"] == "fail"
    assert "lineage/unbound_reference" in _codes(result)
    assert messages
    assert all("could not be located for binding" in message for message in messages)
    assert all(
        "is not bound to the metric definition content" not in message
        for message in messages
    )
    _assert_asos_control()
