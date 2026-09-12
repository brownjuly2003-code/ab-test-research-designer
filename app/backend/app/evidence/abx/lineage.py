"""What is bound to what, and the verdict record that says so.

Reference integrity and lineage are the same walk over the same
documents, so they are checked together and reported separately."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from app.backend.app.evidence._common import (
    SHA256_RE,
)
from app.backend.app.evidence.abx._core import (
    UNBOUND_REFERENCE,
    VERDICT_DIMENSIONS,
    _canonical_digest,
    _is_content_bound_digest,
    _metric_definition_content,
    _query_identity_digest,
    _schema_errors,
)
from app.backend.app.evidence.abx.privacy import _privacy_issues
from app.backend.app.evidence.decision_statement import (
    DECISION_RECORD_SCHEMA_ID,
    DECISION_STATEMENT_SCHEMA_ID,
    DecisionStatementError,
    parse_decision_artifact,
)


def _base_result(archive_path: Path) -> dict[str, Any]:
    return {
        "archive": str(archive_path),
        "valid": False,
        "abx_version": None,
        "bundle_id": None,
        "run_id": None,
        "verdicts": {
            "integrity": "not_checked",
            "schema_conformance": "not_checked",
            "reference_integrity": "not_checked",
            "lineage": "not_checked",
            "privacy_policy": "not_checked",
            "signature": "not_present",
            "statistical_validity": "not_asserted",
        },
        "errors": [],
        "statement": None,
        "unbound_bindings": None,
    }


def _record_error(
    result: dict[str, Any], dimension: str, code: str, message: str, path: str | None = None
) -> None:
    error: dict[str, Any] = {"code": code, "dimension": dimension, "message": message}
    if path:
        error["path"] = path
    cast(list[dict[str, Any]], result["errors"]).append(error)
    cast(dict[str, str], result["verdicts"])[dimension] = "fail"


def _record_unbound_reference(
    result: dict[str, Any], message: str, path: str | None = None
) -> None:
    _record_error(result, "lineage", UNBOUND_REFERENCE, message, path)


def _record_unbound_binding(result: dict[str, Any], path: str) -> None:
    bindings = result.get("unbound_bindings")
    if bindings is None:
        bindings = []
        result["unbound_bindings"] = bindings
    typed = cast(list[str], bindings)
    if path not in typed:
        typed.append(path)


def _prepare_decision_document(
    manifest: dict[str, Any],
    entry: dict[str, Any],
    document: dict[str, Any],
    result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
    schema_id = cast(str | None, entry.get("schema_id"))
    if schema_id != DECISION_STATEMENT_SCHEMA_ID:
        return document, None
    path = cast(str, entry["path"])
    try:
        decision, statement, subject_bundle_id = parse_decision_artifact(
            document,
            schema_id=schema_id,
        )
    except DecisionStatementError as error:
        _record_error(
            result,
            "schema_conformance",
            "artifact_schema",
            str(error),
            path + "/payload",
        )
        return None
    assert statement is not None
    assert subject_bundle_id is not None
    for pointer, message in _schema_errors(decision, DECISION_RECORD_SCHEMA_ID):
        _record_error(
            result,
            "schema_conformance",
            "artifact_schema",
            message,
            path + "/payload/predicate" + pointer,
        )
    for pointer, message in _privacy_issues(statement):
        _record_error(
            result,
            "privacy_policy",
            "sensitive_value",
            message,
            path + "/payload" + pointer,
        )
    if result["statement"] is None:
        result["statement"] = {
            "payload_type": document["payloadType"],
            "predicate_type": statement["predicateType"],
            "signature_count": len(cast(list[Any], document["signatures"])),
            "subject": subject_bundle_id,
            "subject_matches_supersedes": subject_bundle_id
            == manifest.get("supersedes"),
            "type": statement["_type"],
        }
    return decision, statement


def _finish(result: dict[str, Any], evaluated: set[str]) -> dict[str, Any]:
    verdicts = cast(dict[str, str], result["verdicts"])
    bindings_evaluated = result.get("unbound_bindings") is not None
    for dimension in evaluated:
        if verdicts[dimension] == "not_checked":
            if not bindings_evaluated and dimension in {"lineage", "reference_integrity"}:
                continue
            verdicts[dimension] = "pass"
    result["valid"] = all(verdicts[dimension] == "pass" for dimension in VERDICT_DIMENSIONS)
    cast(list[dict[str, Any]], result["errors"]).sort(
        key=lambda item: (str(item["dimension"]), str(item.get("path", "")), str(item["code"]))
    )
    bindings = result.get("unbound_bindings")
    if bindings is not None:
        result["unbound_bindings"] = sorted(cast(list[str], bindings))
    return result


def _single_document(
    role_documents: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]],
    role: str,
    result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    documents = role_documents.get(role, [])
    if len(documents) != 1:
        _record_error(
            result,
            "reference_integrity",
            "role_cardinality",
            f"expected exactly one {role!r} artifact, found {len(documents)}",
        )
        return None
    return documents[0]


def _id_map(
    documents: list[tuple[dict[str, Any], dict[str, Any]]],
    id_key: str,
    role: str,
    result: dict[str, Any],
) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    output: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for entry, document in documents:
        identifier = document.get(id_key)
        if not isinstance(identifier, str):
            continue
        if identifier in output:
            _record_error(result, "reference_integrity", "duplicate_artifact_id", f"duplicate {role} id {identifier!r}", entry["path"])
        output[identifier] = (entry, document)
    return output


def _check_child_chain(
    manifest: dict[str, Any],
    run: dict[str, Any],
    decisions: dict[str, tuple[dict[str, Any], dict[str, Any]]],
    findings: dict[str, tuple[dict[str, Any], dict[str, Any]]],
    run_path: str,
    result: dict[str, Any],
) -> None:
    """Check a bundle that claims a parent, by whichever route it claims one.

    A child bundle declares its parent through a decision citation or through a
    finding-state transition, never both; either way it has to name a parent
    run, and the manifest `supersedes` has to agree with the citation.
    """

    parent_run_id = run.get("parent_run_id")
    supersedes = manifest.get("supersedes")
    cited_bundle_ids = {
        decision.get("cites_bundle_id") for _, decision in decisions.values()
        if "cites_bundle_id" in decision
    }
    run_extensions = run.get("extensions")
    finding_transition = (
        run_extensions.get("trialmark.finding-state")
        if isinstance(run_extensions, dict)
        else None
    )
    chain_declared = (
        parent_run_id is not None
        or supersedes is not None
        or bool(cited_bundle_ids)
        or finding_transition is not None
    )
    if chain_declared:
        if not isinstance(parent_run_id, str):
            _record_unbound_reference(
                result, "child bundle chain has no parent_run_id", run_path
            )
        elif parent_run_id == run.get("run_id"):
            _record_error(
                result,
                "reference_integrity",
                "decision_parent_cycle",
                "child run names itself as its parent",
                run_path,
            )
        parent_bundle_id: object | None = None
        if decisions:
            if finding_transition is not None:
                _record_error(
                    result,
                    "reference_integrity",
                    "finding_transition",
                    "decision child run also declares a finding-state transition",
                    run_path,
                )
            if len(decisions) != 1 or len(cited_bundle_ids) != 1:
                _record_unbound_reference(
                    result,
                    "decision child run must contain one parent bundle citation",
                    run_path,
                )
            else:
                parent_bundle_id = next(iter(cited_bundle_ids))
        else:
            required_transition_keys = {
                "action",
                "actor_ref",
                "cites_bundle_id",
                "finding_id",
                "recorded_at",
                "role",
            }
            if (
                not isinstance(finding_transition, dict)
                or set(finding_transition) != required_transition_keys
            ):
                _record_unbound_reference(
                    result,
                    "finding-state child run has no complete parent bundle transition",
                    run_path,
                )
            else:
                parent_bundle_id = finding_transition["cites_bundle_id"]
                finding_id = finding_transition["finding_id"]
                target_entry = findings.get(finding_id)
                if target_entry is None:
                    _record_error(
                        result,
                        "reference_integrity",
                        "finding_transition",
                        "finding-state transition references an unknown finding",
                        run_path,
                    )
                else:
                    target_manifest_entry, target = target_entry
                    target_path = cast(str, target_manifest_entry["path"])
                    target_extensions = target.get("extensions")
                    target_transition = (
                        target_extensions.get("trialmark.finding-state")
                        if isinstance(target_extensions, dict)
                        else None
                    )
                    if target_transition != finding_transition:
                        _record_unbound_reference(
                            result,
                            "finding-state transition is not bound to its finding",
                            target_path,
                        )
                    if (
                        target.get("produced_at") != finding_transition["recorded_at"]
                        or run.get("completed_at") != finding_transition["recorded_at"]
                    ):
                        _record_error(
                            result,
                            "reference_integrity",
                            "finding_transition",
                            "finding-state transition time does not match its artifacts",
                            target_path,
                        )
                    action = finding_transition["action"]
                    override = target.get("override")
                    if action == "remediate":
                        transition_matches = (
                            target.get("state") == "resolved" and override is None
                        )
                    elif action == "override":
                        transition_matches = (
                            target.get("state") == "overridden"
                            and isinstance(override, dict)
                            and override.get("actor_ref")
                            == finding_transition["actor_ref"]
                            and override.get("recorded_at")
                            == finding_transition["recorded_at"]
                        )
                    else:
                        transition_matches = False
                    if not transition_matches:
                        _record_error(
                            result,
                            "reference_integrity",
                            "finding_transition",
                            "finding-state transition does not match its finding",
                            target_path,
                        )
                if (
                    not isinstance(parent_bundle_id, str)
                    or SHA256_RE.fullmatch(parent_bundle_id) is None
                ):
                    _record_unbound_reference(
                        result,
                        "finding-state transition has an invalid parent bundle citation",
                        run_path,
                    )
        if parent_bundle_id is not None and supersedes != parent_bundle_id:
            _record_unbound_reference(
                result,
                "manifest supersedes is not bound to the child parent bundle citation",
                "manifest.json",
            )


def _check_queries(
    run: dict[str, Any],
    entries_by_path: dict[str, dict[str, Any]],
    sources: dict[str, tuple[dict[str, Any], dict[str, Any]]],
    run_path: str,
    result: dict[str, Any],
) -> set[str]:
    """Bind every declared query to the bundled statement and source it names.

    Returns the query ids, which estimate lineage is later checked against.
    """

    query_ids: set[str] = set()
    declared_query_paths: set[str] = set()
    for query in run.get("queries", []):
        query_id = query.get("query_id")
        statement_path = query.get("statement_path")
        if isinstance(query_id, str):
            if query_id in query_ids:
                _record_error(result, "reference_integrity", "duplicate_query_id", f"duplicate query id {query_id!r}")
            query_ids.add(query_id)
        if isinstance(statement_path, str):
            declared_query_paths.add(statement_path)
        entry = entries_by_path.get(str(statement_path))
        if entry is None or entry.get("role") != "query":
            _record_error(result, "reference_integrity", "missing_query", f"query statement is not bundled: {statement_path!r}")
        elif query.get("statement_digest") != entry.get("digest"):
            _record_unbound_reference(
                result,
                "query statement_digest is not bound to the query bytes",
                str(statement_path),
            )
        query_path = str(statement_path) if isinstance(statement_path, str) else run_path
        if not _is_content_bound_digest(query_id):
            _record_unbound_reference(result, "query_id is degenerate", query_path)
        else:
            source_pair = sources.get(str(query.get("source_snapshot_id")))
            if source_pair is not None:
                expected_query_id = _query_identity_digest(query, source_pair[1])
                if expected_query_id is None or query_id != expected_query_id:
                    _record_unbound_reference(
                        result,
                        "query_id is not bound to the query identity document",
                        query_path,
                    )
        if query.get("source_snapshot_id") not in sources:
            _record_error(result, "reference_integrity", "missing_query_source", "query references an unknown source snapshot")
    bundled_query_paths = {
        path for path, entry in entries_by_path.items() if entry.get("role") == "query"
    }
    if declared_query_paths != bundled_query_paths:
        _record_error(
            result,
            "reference_integrity",
            "run_reference_set",
            "run queries do not match bundled query artifacts",
        )
    return query_ids


def _check_metric_definitions(
    protocol: dict[str, Any],
    run: dict[str, Any],
    role_documents: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]],
    metrics: dict[str, tuple[dict[str, Any], dict[str, Any]]],
    protocol_path: str,
    result: dict[str, Any],
) -> None:
    """Bind each metric definition digest to the definition content it names.

    Both directions are checked: the bundled metric against its own embedded
    definition, and the protocol's reference to that metric against the same
    content.
    """

    protocol_details = cast(dict[str, Any], protocol.get("protocol", {}))
    amendments = role_documents.get("amendments", [])
    if len(amendments) > 1:
        _record_error(result, "reference_integrity", "role_cardinality", "at most one amendments artifact is allowed")
    elif amendments and amendments[0][1].get("protocol_id") != protocol_details.get("protocol_id"):
        _record_error(result, "reference_integrity", "amendment_protocol", "amendments reference a different protocol")

    protocol_metric_refs: list[dict[str, Any]] = []
    metric_groups = cast(dict[str, Any], protocol.get("metrics", {}))
    for group in ("primary", "secondary", "guardrails"):
        protocol_metric_refs.extend(cast(list[dict[str, Any]], metric_groups.get(group, [])))
    referenced_metric_ids = set(run.get("metric_ids", [])) | {
        cast(str, metric_ref["metric_id"]) for metric_ref in protocol_metric_refs
    }
    if set(metrics) - referenced_metric_ids:
        _record_error(
            result,
            "reference_integrity",
            "run_reference_set",
            "bundled metric is not referenced by the run or protocol",
        )
    result["unbound_bindings"] = []
    for metric_entry, metric in role_documents.get("metric", []):
        metric_path = cast(str, metric_entry["path"])
        definition_state, definition = _metric_definition_content(metric)
        if definition_state == "absent":
            _record_unbound_binding(result, metric_path)
            continue
        if definition_state == "ambiguous":
            _record_unbound_binding(result, metric_path)
            _record_unbound_reference(
                result,
                "metric definition_digest cannot be bound to multiple embedded definition payloads",
                metric_path,
            )
            continue
        if definition_state == "unlocated":
            _record_unbound_binding(result, metric_path)
            _record_unbound_reference(
                result,
                "metric definition payload could not be located for binding",
                metric_path,
            )
            continue
        expected_definition = _canonical_digest(definition)
        if expected_definition is None or metric.get("definition_digest") != expected_definition:
            _record_unbound_reference(
                result,
                "metric definition_digest is not bound to the metric definition content",
                metric_path,
            )
    for metric_ref in protocol_metric_refs:
        metric_pair = metrics.get(str(metric_ref.get("metric_id")))
        if metric_pair is None:
            _record_error(result, "reference_integrity", "missing_protocol_metric", "protocol references a metric that is not bundled")
            continue
        _, metric = metric_pair
        if metric_ref.get("metric_version") != metric.get("metric_version"):
            _record_error(
                result,
                "lineage",
                "metric_definition_mismatch",
                "protocol metric version does not match the bundled metric",
            )
        definition_state, definition = _metric_definition_content(metric)
        if definition_state == "absent":
            if metric_ref.get("definition_digest") != metric.get("definition_digest"):
                _record_error(
                    result,
                    "lineage",
                    "metric_definition_mismatch",
                    "protocol metric definition digest does not match the bundled metric",
                )
            continue
        if definition_state in {"ambiguous", "unlocated"}:
            metric_id = metric_ref.get("metric_id")
            if definition_state == "ambiguous":
                protocol_message = (
                    f"protocol metric {metric_id!r} definition_digest cannot be bound to "
                    "multiple embedded definition payloads"
                )
            else:
                protocol_message = (
                    f"protocol metric {metric_id!r} definition payload could not be located for binding"
                )
            _record_unbound_reference(result, protocol_message, protocol_path)
            continue
        expected_definition = _canonical_digest(definition)
        if expected_definition is None or metric_ref.get("definition_digest") != expected_definition:
            _record_unbound_reference(
                result,
                "protocol metric definition_digest is not bound to the metric definition content",
                protocol_path,
            )


def _check_method_profile(
    protocol: dict[str, Any],
    method_profiles: list[tuple[dict[str, Any], dict[str, Any]]],
    run_runner: dict[str, Any],
    run_path: str,
    result: dict[str, Any],
) -> None:
    """Check the method profile against the frozen protocol and the run build."""

    if len(method_profiles) == 1:
        method_entry, method_profile = method_profiles[0]
        analysis = cast(dict[str, Any], protocol.get("analysis", {}))
        protocol_method = cast(dict[str, Any], analysis.get("method", {}))
        profile_matches = (
            method_profile.get("method_id") == protocol_method.get("method_id")
            and method_profile.get("method_version")
            == protocol_method.get("method_version")
            and method_profile.get("implementation_digest")
            == run_runner.get("build_digest")
            and method_profile.get("error_control", {}).get("nominal_alpha")
            == float(cast(str, analysis.get("alpha")))
        )
        if not profile_matches:
            _record_error(
                result,
                "lineage",
                "method_profile_mismatch",
                "method profile does not match the frozen protocol and run build",
                method_entry["path"],
            )
    for digest_key in ("build_digest", "dependency_lock_digest"):
        if not _is_content_bound_digest(run_runner.get(digest_key)):
            _record_unbound_reference(
                result,
                f"run runner {digest_key} is a degenerate placeholder digest, not a content digest",
                run_path,
            )


def _check_references(
    manifest: dict[str, Any],
    role_documents: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]],
    entries_by_path: dict[str, dict[str, Any]],
    result: dict[str, Any],
) -> None:
    protocol_pair = _single_document(role_documents, "protocol", result)
    run_pair = _single_document(role_documents, "run", result)
    if protocol_pair is None or run_pair is None:
        return
    protocol_entry, protocol = protocol_pair
    run_entry, run = run_pair
    protocol_digest = _canonical_digest(protocol)
    protocol_path = cast(str, protocol_entry["path"])
    run_path = cast(str, run_entry["path"])

    sources = _id_map(role_documents.get("source", []), "source_snapshot_id", "source", result)
    metrics = _id_map(role_documents.get("metric", []), "metric_id", "metric", result)
    findings = _id_map(role_documents.get("finding", []), "finding_id", "finding", result)
    estimates = _id_map(role_documents.get("estimate", []), "estimate_id", "estimate", result)
    decisions = _id_map(role_documents.get("decision", []), "decision_id", "decision", result)
    decision_statements = role_documents.get("_decision_statement", [])
    method_profiles = role_documents.get("method", [])
    if len(method_profiles) > 1:
        _record_error(
            result,
            "reference_integrity",
            "role_cardinality",
            "at most one method profile artifact is allowed",
        )

    if manifest.get("run_id") != run.get("run_id"):
        _record_error(
            result,
            "reference_integrity",
            "manifest_run_id",
            f"manifest value {manifest.get('run_id')!r} does not match run value {run.get('run_id')!r}",
        )
    if protocol_digest is None:
        _record_unbound_reference(
            result,
            "protocol document is not RFC 8785 canonicalizable",
            protocol_path,
        )
    else:
        if manifest.get("protocol_revision_id") != protocol_digest:
            _record_unbound_reference(
                result,
                "manifest protocol_revision_id is not bound to the protocol content digest",
                "manifest.json",
            )
        if run.get("protocol_revision_id") != protocol_digest:
            _record_unbound_reference(
                result,
                "run protocol_revision_id is not bound to the protocol content digest",
                run_path,
            )

    set_checks = (
        ("source_snapshot_ids", set(sources)),
        ("metric_ids", set(run.get("metric_ids", [])) & set(metrics)),
        ("finding_ids", set(findings)),
        ("estimate_ids", set(estimates)),
    )
    for key, bundled_ids in set_checks:
        declared = set(run.get(key, []))
        if declared != bundled_ids:
            _record_error(result, "reference_integrity", "run_reference_set", f"run {key} does not match bundled artifacts")
    if set(run.get("metric_ids", [])) - set(metrics):
        _record_error(result, "reference_integrity", "missing_metric", "run references a metric that is not bundled")

    decision_id = run.get("decision_id")
    expected_decisions = set() if decision_id is None else {decision_id}
    if expected_decisions != set(decisions):
        _record_error(result, "reference_integrity", "decision_reference", "run decision_id does not match the bundled decision")
    for statement_entry, statement in decision_statements:
        subject = cast(list[dict[str, Any]], statement["subject"])[0]
        subject_digest = cast(dict[str, Any], subject["digest"])["sha256"]
        subject_bundle_id = f"sha256:{subject_digest}"
        predicate = cast(dict[str, Any], statement["predicate"])
        if predicate.get("cites_bundle_id") != subject_bundle_id:
            _record_unbound_reference(
                result,
                "decision statement subject is not bound to its parent bundle citation",
                cast(str, statement_entry["path"]),
            )
        if manifest.get("supersedes") != subject_bundle_id:
            _record_unbound_reference(
                result,
                "decision statement subject is not bound to manifest supersedes",
                cast(str, statement_entry["path"]),
            )

    _check_child_chain(manifest, run, decisions, findings, run_path, result)

    query_ids = _check_queries(
        run, entries_by_path, sources, run_path, result
    )

    _check_metric_definitions(
        protocol, run, role_documents, metrics, protocol_path, result
    )

    intervention_ids = {
        item.get("intervention_id") for item in protocol.get("interventions", []) if isinstance(item, dict)
    }
    protocol_estimand = cast(dict[str, Any], protocol.get("estimand", {}))
    run_runner = cast(dict[str, Any], run.get("runner", {}))
    _check_method_profile(
        protocol, method_profiles, run_runner, run_path, result
    )
    manifest_digests = {entry["digest"] for entry in entries_by_path.values()}
    for entry, estimate in role_documents.get("estimate", []):
        if estimate.get("run_id") != run.get("run_id"):
            _record_error(result, "reference_integrity", "estimate_run", "estimate references a different run", entry["path"])
        if estimate.get("estimand_id") != protocol_estimand.get("estimand_id"):
            _record_error(result, "lineage", "estimate_estimand", "estimate references a different estimand", entry["path"])
        contrast = cast(dict[str, Any], estimate.get("contrast", {}))
        if not {contrast.get("baseline_intervention_id"), contrast.get("comparison_intervention_id")} <= intervention_ids:
            _record_error(result, "reference_integrity", "estimate_intervention", "estimate contrast references an unknown intervention", entry["path"])
        lineage = cast(dict[str, Any], estimate.get("lineage", {}))
        if protocol_digest is None or lineage.get("protocol_revision_id") != protocol_digest:
            _record_unbound_reference(
                result,
                "estimate lineage protocol_revision_id is not bound to the protocol content digest",
                entry["path"],
            )
        metric_lineage = cast(dict[str, Any], lineage.get("metric", {}))
        metric_pair = metrics.get(str(metric_lineage.get("metric_id")))
        if metric_pair is None:
            _record_error(result, "reference_integrity", "estimate_metric", "estimate lineage references an unknown metric", entry["path"])
        else:
            metric_entry, metric = metric_pair
            # Packing stores pretty-printed metric JSON and hashes those member bytes.
            # Integrity already binds metric_entry["digest"] to those saved bytes.
            if metric_lineage.get("metric_version") != metric.get("metric_version"):
                _record_error(
                    result,
                    "lineage",
                    "estimate_metric_lineage",
                    "estimate metric lineage does not match the bundled metric",
                    entry["path"],
                )
            if metric_lineage.get("metric_digest") != metric_entry.get("digest"):
                _record_unbound_reference(
                    result,
                    "estimate metric_digest is not bound to the metric content",
                    entry["path"],
                )
        if not set(lineage.get("query_ids", [])) <= query_ids:
            _record_error(result, "reference_integrity", "estimate_query", "estimate lineage references an unknown query", entry["path"])
        if not set(lineage.get("source_snapshot_ids", [])) <= set(sources):
            _record_error(result, "reference_integrity", "estimate_source", "estimate lineage references an unknown source", entry["path"])
        estimate_runner = cast(dict[str, Any], lineage.get("runner", {}))
        if any(run_runner.get(key) != value for key, value in estimate_runner.items()):
            _record_error(result, "lineage", "estimate_runner", "estimate runner lineage does not match the run", entry["path"])

    for entry, finding in role_documents.get("finding", []):
        if finding.get("run_id") != run.get("run_id"):
            _record_error(result, "reference_integrity", "finding_run", "finding references a different run", entry["path"])
        for evidence in finding.get("evidence", []):
            if evidence.get("artifact_digest") not in manifest_digests:
                _record_error(result, "lineage", "finding_evidence", "finding evidence digest is not bundled", entry["path"])

    for entry, decision in role_documents.get("decision", []):
        if decision.get("run_id") != run.get("run_id"):
            _record_error(
                result,
                "reference_integrity",
                "decision_context",
                "decision references a different run",
                entry["path"],
            )
        if protocol_digest is None or decision.get("protocol_revision_id") != protocol_digest:
            _record_unbound_reference(
                result,
                "decision protocol_revision_id is not bound to the protocol content digest",
                entry["path"],
            )
        evidence = cast(dict[str, Any], decision.get("evidence", {}))
        if not set(evidence.get("estimate_ids", [])) <= set(estimates) or not set(evidence.get("finding_ids", [])) <= set(findings):
            _record_error(result, "reference_integrity", "decision_evidence", "decision references evidence that is not bundled", entry["path"])
