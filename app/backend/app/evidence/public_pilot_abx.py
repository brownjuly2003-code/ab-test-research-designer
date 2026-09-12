from __future__ import annotations

import json
import math
import tempfile
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import NormalDist
from typing import Any, Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.backend.app.evidence._common import (
    canonical_digest,
    canonical_json_bytes,
    sha256_hex,
)
from app.backend.app.evidence.abx import (
    ABX_VERSION,
    MANIFEST_SCHEMA_ID,
    pack_bundle,
    validate_abx_document,
)
from app.backend.app.evidence.public_pilots import (
    ASOS_DATASET_DOI,
    ASOS_DATASET_NAME,
    ASOS_DATASET_URL,
    ASOS_LICENSE,
    AsosMetricSnapshot,
    AsosPublicPilot,
    load_asos_public_pilot,
)
from app.backend.app.stats.binary import standard_normal_sf

_SCHEMA_PREFIX: Final = "urn:evidenceos:abx:schema:0.1:"
_SOURCE_SCHEMA_ID: Final = _SCHEMA_PREFIX + "source"
_METRIC_SCHEMA_ID: Final = _SCHEMA_PREFIX + "metric"
_ESTIMATE_SCHEMA_ID: Final = _SCHEMA_PREFIX + "estimate"
_RUN_SCHEMA_ID: Final = _SCHEMA_PREFIX + "run"
_BENCHMARK_EXTENSION: Final = "trialmark.asos"
_AGGREGATE_INPUTS_EXTENSION: Final = "trialmark.aggregate-inputs"
_RUNNER_SOURCE_PATHS: Final = (
    "app/evidence/public_pilot_abx.py",
    "app/evidence/public_pilots.py",
)
_ACTOR_PATTERN: Final = r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$"
_FIELD_PATTERN: Final = r"^[A-Za-z_][A-Za-z0-9_.-]*$"
_METHOD_PATTERN: Final = r"^[a-z][a-z0-9_]*$"
_NORMAL = NormalDist()
# Significant digits kept in a benchmark p-value. The p-value is the one field in
# these documents that leaves IEEE-754 arithmetic: it comes from erfc, which every
# platform implements in its own libm, and the last two or three digits differ
# between them. Every other float here is sums, quotients and sqrt, all of which
# are bit-exact everywhere, and inv_cdf is a pure-Python rational approximation.
# Rounding the p-value to twelve digits -- ten orders below any statistical
# meaning, four orders above the observed libm spread -- is what keeps the bundle
# ID a property of the evidence rather than of the machine that packed it.
_BENCHMARK_P_VALUE_DIGITS: Final = 12


def _benchmark_p_value(value: float) -> float:
    return float(f"{value:.{_BENCHMARK_P_VALUE_DIGITS}g}")


class AsosPublicPilotAbxError(ValueError):
    """Raised when a public benchmark cannot be represented honestly as ABX."""


class AsosPublicPilotAbxContext(BaseModel):
    """Caller-owned retrospective harness semantics missing from the ASOS extract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"]
    artifact_created_at: str = Field(min_length=1)
    protocol_created_at: str = Field(min_length=1)
    protocol_frozen_at: str = Field(min_length=1)
    source_captured_at: str = Field(min_length=1)
    run_started_at: str = Field(min_length=1)
    run_completed_at: str = Field(min_length=1)
    estimate_produced_at: str = Field(min_length=1)
    evidence_type: Literal["public_benchmark"]
    partner_approved: Literal[False]
    original_protocol_available: Literal[False]
    original_metric_semantics_available: Literal[False]
    timing_is_partner_evidence: Literal[False]
    retrospective_protocol_harness: Literal[True]
    owner_ref: str = Field(pattern=_ACTOR_PATTERN)
    population_eligibility: str = Field(min_length=1, max_length=4096)
    population_trigger: str = Field(min_length=1, max_length=4096)
    randomization_unit: Literal["user", "session", "account", "device", "cluster"]
    analysis_population: Literal["intention_to_treat", "per_protocol", "exposed"]
    experiment_type: Literal["randomized", "cluster_randomized", "switchback", "factorial"]
    interference_assumption: Literal[
        "no_interference", "partial_interference", "interference_expected"
    ]
    exposure_semantics: str = Field(min_length=1, max_length=4096)
    allocation_control: str = Field(min_length=1)
    allocation_treatment: str = Field(min_length=1)
    missing_data_rule: Literal["exclude", "zero", "censor", "model"]
    horizon_rule: Literal["terminal_checkpoint_from_time_since_start"]
    analysis_method: str = Field(pattern=_METHOD_PATTERN)
    analysis_method_version: str = Field(min_length=1, max_length=64)
    alpha: str = Field(min_length=1)
    power: str = Field(min_length=1)
    stopping_mode: Literal["fixed_horizon"]
    multiplicity_method: Literal["none"]
    variance_reduction_method: Literal["none"]
    telemetry_subject_key: str = Field(pattern=_FIELD_PATTERN)
    telemetry_event_key: str = Field(pattern=_FIELD_PATTERN)
    telemetry_occurred_at_key: str = Field(pattern=_FIELD_PATTERN)
    telemetry_exposure_event: str = Field(pattern=_ACTOR_PATTERN)
    telemetry_outcome_event: str = Field(pattern=_ACTOR_PATTERN)
    telemetry_ordering: Literal["event_time", "ingest_time"]
    telemetry_deduplication_window: str = Field(min_length=1)
    telemetry_max_lateness: str = Field(min_length=1)
    decision_minimum_worthwhile_effect: float
    approval_role: str = Field(pattern=_ACTOR_PATTERN)
    rollback_owner: str = Field(pattern=_ACTOR_PATTERN)
    lag_budget_seconds: int = Field(ge=0, le=31_536_000)

    @model_validator(mode="after")
    def validate_context_contract(self) -> AsosPublicPilotAbxContext:
        timestamp_names = (
            "artifact_created_at",
            "protocol_created_at",
            "protocol_frozen_at",
            "source_captured_at",
            "run_started_at",
            "run_completed_at",
            "estimate_produced_at",
        )
        timestamps: dict[str, datetime] = {}
        for name in timestamp_names:
            raw = cast(str, getattr(self, name))
            if not raw.endswith("Z"):
                raise ValueError(f"{name} must be an explicit UTC timestamp ending in Z")
            try:
                parsed = datetime.fromisoformat(raw[:-1] + "+00:00")
            except ValueError as error:
                raise ValueError(f"{name} must be an ISO 8601 timestamp") from error
            timestamps[name] = parsed

        if not (
            timestamps["protocol_created_at"]
            <= timestamps["protocol_frozen_at"]
            <= timestamps["run_started_at"]
            <= timestamps["run_completed_at"]
        ):
            raise ValueError("protocol and run timestamps must be ordered")
        if not (
            timestamps["run_started_at"]
            <= timestamps["source_captured_at"]
            <= timestamps["run_completed_at"]
        ):
            raise ValueError("source_captured_at must fall within the benchmark run")
        if not (
            timestamps["run_started_at"]
            <= timestamps["estimate_produced_at"]
            <= timestamps["run_completed_at"]
        ):
            raise ValueError("estimate_produced_at must fall within the benchmark run")
        if timestamps["artifact_created_at"] < timestamps["run_completed_at"]:
            raise ValueError("artifact_created_at must not precede run_completed_at")

        control = _probability(self.allocation_control, field="allocation_control")
        treatment = _probability(self.allocation_treatment, field="allocation_treatment")
        if control <= 0 or treatment <= 0 or control + treatment != Decimal(1):
            raise ValueError("benchmark allocations must be positive and sum exactly to 1")
        _probability(self.alpha, field="alpha", exclusive=True)
        _probability(self.power, field="power", exclusive=True)
        return self


def _probability(value: str, *, field: str, exclusive: bool = False) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{field} must be a decimal probability string") from error
    if not parsed.is_finite() or parsed < 0 or parsed > 1:
        raise ValueError(f"{field} must be between 0 and 1")
    if exclusive and parsed in {Decimal(0), Decimal(1)}:
        raise ValueError(f"{field} must be strictly between 0 and 1")
    return parsed


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AsosPublicPilotAbxError(f"benchmark context contains duplicate key {key!r}")
        result[key] = value
    return result


def _reject_non_json_number(value: str) -> None:
    raise AsosPublicPilotAbxError(f"benchmark context contains non-JSON number {value!r}")


def load_asos_public_pilot_abx_context(path: Path | str) -> AsosPublicPilotAbxContext:
    """Load and freeze the explicit retrospective benchmark harness context."""

    context_path = Path(path)
    try:
        payload = json.loads(
            context_path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_json_number,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AsosPublicPilotAbxError("unable to read the ASOS ABX benchmark context") from error
    if not isinstance(payload, dict):
        raise AsosPublicPilotAbxError("ASOS ABX benchmark context must be a JSON object")
    return AsosPublicPilotAbxContext.model_validate(payload)


def _decimal_string(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _terminal_horizon(days: float) -> str:
    seconds_value = days * 86_400
    total_seconds = round(seconds_value)
    if total_seconds <= 0 or not math.isclose(
        seconds_value,
        total_seconds,
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        raise AsosPublicPilotAbxError(
            "terminal checkpoint must resolve to a positive whole-second duration"
        )
    day_count, remainder = divmod(total_seconds, 86_400)
    hour_count, remainder = divmod(remainder, 3_600)
    minute_count, second_count = divmod(remainder, 60)
    duration = f"P{day_count}D" if day_count else "P"
    if hour_count or minute_count or second_count:
        duration += "T"
        if hour_count:
            duration += f"{hour_count}H"
        if minute_count:
            duration += f"{minute_count}M"
        if second_count:
            duration += f"{second_count}S"
    return duration


def _benchmark_details(
    pilot: AsosPublicPilot,
    context: AsosPublicPilotAbxContext,
) -> dict[str, Any]:
    return {
        "dataset_doi": ASOS_DATASET_DOI,
        "dataset_name": ASOS_DATASET_NAME,
        "dataset_url": ASOS_DATASET_URL,
        "evidence_type": context.evidence_type,
        "experiment_id": pilot.metadata.experiment_id,
        "license": ASOS_LICENSE,
        "original_metric_semantics_available": context.original_metric_semantics_available,
        "original_protocol_available": context.original_protocol_available,
        "partner_approved": context.partner_approved,
        "retrospective_protocol_harness": context.retrospective_protocol_harness,
        "timing_is_partner_evidence": context.timing_is_partner_evidence,
    }


def _extensions(
    pilot: AsosPublicPilot,
    context: AsosPublicPilotAbxContext,
    **details: Any,
) -> dict[str, Any]:
    benchmark = _benchmark_details(pilot, context)
    benchmark.update(details)
    return {_BENCHMARK_EXTENSION: benchmark}


def _source_document(
    pilot: AsosPublicPilot,
    context: AsosPublicPilotAbxContext,
    source_snapshot_id: str,
) -> dict[str, Any]:
    return {
        "schema_version": ABX_VERSION,
        "source_snapshot_id": source_snapshot_id,
        "source_ref": pilot.inspection.source_ref,
        "kind": "duckdb_file",
        "captured_at": context.source_captured_at,
        "fingerprint": pilot.inspection.fingerprint.model_dump(mode="json"),
        "engine": pilot.inspection.engine.model_dump(mode="json"),
        "schema_digest": pilot.inspection.schema_digest,
        "extensions": _extensions(
            pilot,
            context,
            aggregate_only=True,
            derived_fixture_sha256=pilot.inspection.fingerprint.value,
            fixture_row_count=pilot.inspection.estimated_rows,
            upstream_source_sha256=pilot.metadata.source_sha256,
        ),
    }


def _metric_document(
    pilot: AsosPublicPilot,
    context: AsosPublicPilotAbxContext,
    source_snapshot_id: str,
    snapshot: AsosMetricSnapshot,
) -> dict[str, Any]:
    metric_id = f"metric_asos_{snapshot.metric_id}"
    kind = {
        "binary": "binary",
        "count": "count",
        "nonnegative_real": "continuous",
    }[snapshot.metric_kind]
    definition = {
        "aggregation": "terminal_sample_mean",
        "dataset_doi": ASOS_DATASET_DOI,
        "metric_id": snapshot.metric_id,
        "original_semantics_available": False,
        "reported_kind": snapshot.metric_kind,
    }
    return {
        "schema_version": ABX_VERSION,
        "metric_id": metric_id,
        "metric_version": "public-benchmark-v1",
        "definition_digest": canonical_digest(definition),
        "name": f"ASOS decision metric {snapshot.metric_id}",
        "kind": kind,
        "direction": "neutral",
        "unit": "published_response_unit",
        "aggregation": "mean",
        "owner_ref": context.owner_ref,
        "source_snapshot_id": source_snapshot_id,
        "extensions": _extensions(
            pilot,
            context,
            aggregate_only=True,
            definition=definition,
        ),
    }


def _protocol_document(
    pilot: AsosPublicPilot,
    context: AsosPublicPilotAbxContext,
    metric_documents: list[dict[str, Any]],
) -> dict[str, Any]:
    experiment_id = pilot.metadata.experiment_id
    metric_references = [
        {
            "metric_id": metric["metric_id"],
            "metric_version": metric["metric_version"],
            "definition_digest": metric["definition_digest"],
        }
        for metric in metric_documents
    ]
    horizon = _terminal_horizon(pilot.snapshots[0].time_since_start)
    exposure_schema_digest = canonical_digest(
        {
            "event_type": context.telemetry_exposure_event,
            "semantics": "retrospective aggregate harness",
        }
    )
    outcome_schema_digest = canonical_digest(
        {
            "event_type": context.telemetry_outcome_event,
            "semantics": "retrospective aggregate harness",
        }
    )
    return {
        "spec_version": ABX_VERSION,
        "required_capabilities": ["protocol-core"],
        "protocol": {
            "protocol_id": f"asos-public-benchmark-{experiment_id}",
            "title": f"ASOS public benchmark {experiment_id}",
            "hypothesis": (
                "The retrospective harness can reproduce terminal aggregate mean contrasts "
                "without reconstructing the original experiment protocol or metric semantics."
            ),
            "owners": [context.owner_ref],
            "created_at": context.protocol_created_at,
        },
        "freeze": {
            "state": "frozen",
            "frozen_by": context.owner_ref,
            "frozen_at": context.protocol_frozen_at,
        },
        "population": {
            "eligibility_expression": context.population_eligibility,
            "trigger_expression": context.population_trigger,
            "randomization_unit": context.randomization_unit,
            "analysis_population": context.analysis_population,
            "exclusions": ["Raw user-level records are unavailable in the public dataset."],
        },
        "interventions": [
            {
                "intervention_id": "control",
                "label": "Published control aggregate",
                "kind": "control",
                "allocation": context.allocation_control,
                "namespace": f"asos_public_benchmark_{experiment_id}",
                "hash_version": "unavailable_public_dataset",
            },
            {
                "intervention_id": "treatment",
                "label": f"Published treatment variant {pilot.metadata.treatment_variant_id}",
                "kind": "treatment",
                "allocation": context.allocation_treatment,
                "namespace": f"asos_public_benchmark_{experiment_id}",
                "hash_version": "unavailable_public_dataset",
            },
        ],
        "metrics": {
            "primary": metric_references[:1],
            "secondary": metric_references[1:],
            "guardrails": [],
        },
        "estimand": {
            "estimand_id": f"estimand_asos_{experiment_id}_terminal",
            "population": context.analysis_population,
            "baseline_intervention_id": "control",
            "comparison_intervention_ids": ["treatment"],
            "effect_measure": "mean_difference",
            "horizon": horizon,
            "missing_data_rule": context.missing_data_rule,
        },
        "design": {
            "experiment_type": context.experiment_type,
            "interference_assumption": context.interference_assumption,
            "exposure_semantics": context.exposure_semantics,
        },
        "analysis": {
            "method": {
                "method_id": context.analysis_method,
                "method_version": context.analysis_method_version,
            },
            "alpha": context.alpha,
            "power": context.power,
            "stopping": {"mode": context.stopping_mode, "look_count": 1},
            "multiplicity": {"method": context.multiplicity_method, "family_ids": []},
            "variance_reduction": {
                "method": context.variance_reduction_method,
                "covariate_metric_ids": [],
            },
        },
        "telemetry": {
            "subject_key": context.telemetry_subject_key,
            "event_key": context.telemetry_event_key,
            "occurred_at_key": context.telemetry_occurred_at_key,
            "exposure_event": context.telemetry_exposure_event,
            "outcome_events": [context.telemetry_outcome_event],
            "ordering": context.telemetry_ordering,
            "deduplication": {
                "keys": [context.telemetry_event_key],
                "window": context.telemetry_deduplication_window,
            },
            "max_lateness": context.telemetry_max_lateness,
            "schema_versions": [
                {
                    "event_type": context.telemetry_exposure_event,
                    "version": "benchmark-v1",
                    "schema_digest": exposure_schema_digest,
                },
                {
                    "event_type": context.telemetry_outcome_event,
                    "version": "benchmark-v1",
                    "schema_digest": outcome_schema_digest,
                },
            ],
        },
        "decision": {
            "minimum_worthwhile_effect": context.decision_minimum_worthwhile_effect,
            "harm_rules": [],
            "owners": [context.owner_ref],
            "approval_policy": {"roles": [context.approval_role], "minimum_approvals": 1},
        },
        "operations": {
            "rollback_owner": context.rollback_owner,
            "lag_budget_seconds": context.lag_budget_seconds,
            "alert_thresholds": [],
        },
        "extensions": _extensions(
            pilot,
            context,
            allocation_basis="explicit_benchmark_harness_assumption",
            decision_use="not_for_product_decision",
            horizon_basis=context.horizon_rule,
            telemetry_basis="retrospective_aggregate_mapping",
        ),
    }


def _runner_document(context: AsosPublicPilotAbxContext) -> dict[str, Any]:
    backend_root = Path(__file__).resolve().parents[2]
    try:
        source_records = [
            {
                "path": relative_path,
                "digest": sha256_hex((backend_root / relative_path).read_bytes()),
            }
            for relative_path in _RUNNER_SOURCE_PATHS
        ]
        dependency_digest = sha256_hex((backend_root / "requirements.txt").read_bytes())
    except OSError as error:
        raise AsosPublicPilotAbxError("runner source or backend dependency lock is unavailable") from error
    return {
        "name": "trialmark-public-benchmark",
        "version": "0.1.0",
        "build_digest": canonical_digest({"sources": source_records}),
        "dependency_lock_digest": dependency_digest,
        "analyzer_version": context.analysis_method_version,
        "policy_version": "public-benchmark-v1",
    }


def _estimate_document(
    pilot: AsosPublicPilot,
    context: AsosPublicPilotAbxContext,
    snapshot: AsosMetricSnapshot,
    *,
    metric_digest: str,
    protocol_revision_id: str,
    query_id: str,
    run_id: str,
    runner: dict[str, Any],
    source_snapshot_id: str,
) -> dict[str, Any]:
    variance = snapshot.variance_c / snapshot.count_c + snapshot.variance_t / snapshot.count_t
    standard_error = math.sqrt(max(variance, 0.0))
    point_estimate = snapshot.mean_t - snapshot.mean_c
    alpha = float(_probability(context.alpha, field="alpha", exclusive=True))
    critical_value = _NORMAL.inv_cdf(1.0 - alpha / 2.0)
    if standard_error == 0.0:
        p_value = 1.0 if point_estimate == 0.0 else 0.0
    else:
        p_value = 2.0 * standard_normal_sf(abs(point_estimate / standard_error))
    p_value = _benchmark_p_value(min(1.0, max(0.0, p_value)))
    metric_id = f"metric_asos_{snapshot.metric_id}"
    document: dict[str, Any] = {
        "schema_version": ABX_VERSION,
        "estimate_id": f"estimate_asos_{pilot.metadata.experiment_id}_{snapshot.metric_id}",
        "content_digest": "sha256:" + "0" * 64,
        "run_id": run_id,
        "estimand_id": f"estimand_asos_{pilot.metadata.experiment_id}_terminal",
        "contrast": {
            "baseline_intervention_id": "control",
            "comparison_intervention_id": "treatment",
        },
        "effect_measure": "mean_difference",
        "point_estimate": point_estimate,
        "uncertainty": {
            "kind": "confidence_interval",
            "level": _decimal_string(Decimal(1) - Decimal(context.alpha)),
            "lower": point_estimate - critical_value * standard_error,
            "upper": point_estimate + critical_value * standard_error,
            "standard_error": standard_error,
            "p_value": p_value,
        },
        "sample_size": {
            "total": snapshot.count_c + snapshot.count_t,
            "groups": {"control": snapshot.count_c, "treatment": snapshot.count_t},
        },
        "lineage": {
            "protocol_revision_id": protocol_revision_id,
            "metric": {
                "metric_id": metric_id,
                "metric_version": "public-benchmark-v1",
                "metric_digest": metric_digest,
            },
            "query_ids": [query_id],
            "source_snapshot_ids": [source_snapshot_id],
            "runner": runner,
        },
        "produced_at": context.estimate_produced_at,
        "extensions": {
            _AGGREGATE_INPUTS_EXTENSION: {
                "count_c": snapshot.count_c,
                "count_t": snapshot.count_t,
                "mean_c": snapshot.mean_c,
                "mean_t": snapshot.mean_t,
                "variance_c": snapshot.variance_c,
                "variance_t": snapshot.variance_t,
            },
            **_extensions(
                pilot,
                context,
                aggregate_only=True,
                uncertainty_method="normal_mean_difference",
            ),
        },
    }
    digest_core = {key: value for key, value in document.items() if key != "content_digest"}
    document["content_digest"] = canonical_digest(digest_core)
    return document


def _write_payload(root: Path, relative_path: str, payload: bytes) -> None:
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def pack_asos_public_pilot_abx(
    fixture_path: Path | str,
    *,
    context: AsosPublicPilotAbxContext,
    destination: Path | str,
    expected_experiment_id: str,
) -> dict[str, Any]:
    """Pack one deterministic, aggregate-only ASOS retrospective benchmark bundle."""

    pilot = load_asos_public_pilot(
        fixture_path,
        expected_experiment_id=expected_experiment_id,
    )
    experiment_id = pilot.metadata.experiment_id
    source_snapshot_id = f"source_asos_{experiment_id}_terminal"
    run_id = f"run_asos_{experiment_id}_terminal"
    metric_documents = [
        _metric_document(pilot, context, source_snapshot_id, snapshot)
        for snapshot in pilot.snapshots
    ]
    protocol = _protocol_document(pilot, context, metric_documents)
    protocol_revision_id = canonical_digest(protocol)
    source = _source_document(pilot, context, source_snapshot_id)
    runner = _runner_document(context)

    query_payload = pilot.provenance.statement.encode("utf-8")
    if sha256_hex(query_payload) != pilot.provenance.statement_digest:
        raise AsosPublicPilotAbxError("terminal query payload does not match its provenance digest")
    query_path = (
        "queries/" + pilot.provenance.statement_digest.removeprefix("sha256:") + ".sql"
    )

    payloads: dict[str, bytes] = {}
    roles: dict[str, str] = {}

    def add_document(relative_path: str, role: str, document: dict[str, Any]) -> str:
        schema_id = _SCHEMA_PREFIX + role
        validate_abx_document(document, schema_id)
        payload = canonical_json_bytes(document)
        payloads[relative_path] = payload
        roles[relative_path] = role
        return sha256_hex(payload)

    add_document("protocol/protocol.json", "protocol", protocol)
    add_document(f"sources/source_asos_{experiment_id}.json", "source", source)

    metric_digests: dict[str, str] = {}
    for metric in metric_documents:
        metric_id = cast(str, metric["metric_id"])
        path = f"metrics/{metric_id}.json"
        metric_digests[metric_id] = add_document(path, "metric", metric)

    estimate_documents = [
        _estimate_document(
            pilot,
            context,
            snapshot,
            metric_digest=metric_digests[f"metric_asos_{snapshot.metric_id}"],
            protocol_revision_id=protocol_revision_id,
            query_id=pilot.provenance.query_id,
            run_id=run_id,
            runner=runner,
            source_snapshot_id=source_snapshot_id,
        )
        for snapshot in pilot.snapshots
    ]
    for estimate in estimate_documents:
        estimate_id = cast(str, estimate["estimate_id"])
        add_document(f"estimates/{estimate_id}.json", "estimate", estimate)

    payloads[query_path] = query_payload
    roles[query_path] = "query"
    run = {
        "schema_version": ABX_VERSION,
        "required_capabilities": ["lineage-v1", "protocol-core"],
        "run_id": run_id,
        "protocol_revision_id": protocol_revision_id,
        "kind": "analysis",
        "status": "succeeded",
        "started_at": context.run_started_at,
        "completed_at": context.run_completed_at,
        "runner": runner,
        "source_snapshot_ids": [source_snapshot_id],
        "metric_ids": [cast(str, metric["metric_id"]) for metric in metric_documents],
        "queries": [
            {
                "query_id": pilot.provenance.query_id,
                "source_snapshot_id": source_snapshot_id,
                "dialect": pilot.provenance.dialect,
                "statement_path": query_path,
                "statement_digest": pilot.provenance.statement_digest,
                "parameters_digest": pilot.provenance.parameters_digest,
                "input_aggregate_digests": [pilot.inspection.fingerprint.value],
                "extensions": {
                    "trialmark.query-budget": {
                        "estimated_scan_rows": pilot.provenance.estimated_scan_rows,
                    }
                },
            }
        ],
        "finding_ids": [],
        "estimate_ids": [
            cast(str, estimate["estimate_id"]) for estimate in estimate_documents
        ],
        "extensions": _extensions(
            pilot,
            context,
            aggregate_only=True,
            statistical_validity="not_asserted",
        ),
    }
    add_document("run/run.json", "run", run)

    entries: list[dict[str, Any]] = []
    for relative_path in sorted(payloads):
        role = roles[relative_path]
        entry: dict[str, Any] = {
            "path": relative_path,
            "role": role,
            "media_type": "application/sql" if role == "query" else "application/json",
            "size": len(payloads[relative_path]),
            "digest": sha256_hex(payloads[relative_path]),
        }
        if role != "query":
            entry["schema_id"] = _SCHEMA_PREFIX + role
        entries.append(entry)
    if len(entries) != 12:
        raise AsosPublicPilotAbxError("ASOS public benchmark must contain exactly 12 artifacts")

    manifest: dict[str, Any] = {
        "abx_version": ABX_VERSION,
        "bundle_id": "sha256:" + "0" * 64,
        "created_at": context.artifact_created_at,
        "protocol_revision_id": protocol_revision_id,
        "run_id": run_id,
        "hash_algorithm": "sha256",
        "required_capabilities": ["lineage-v1", "protocol-core"],
        "entries": entries,
        "extensions": _extensions(
            pilot,
            context,
            aggregate_only=True,
            decision_artifact_present=False,
            statistical_validity="not_asserted",
        ),
    }
    manifest_core = {key: value for key, value in manifest.items() if key != "bundle_id"}
    manifest["bundle_id"] = canonical_digest(manifest_core)
    validate_abx_document(manifest, MANIFEST_SCHEMA_ID)

    with tempfile.TemporaryDirectory(prefix="trialmark-asos-public-abx-") as temporary_name:
        logical_root = Path(temporary_name) / "logical"
        logical_root.mkdir()
        for relative_path, payload in payloads.items():
            _write_payload(logical_root, relative_path, payload)
        _write_payload(logical_root, "manifest.json", canonical_json_bytes(manifest))
        return pack_bundle(logical_root, destination)


__all__ = [
    "AsosPublicPilotAbxContext",
    "AsosPublicPilotAbxError",
    "load_asos_public_pilot_abx_context",
    "pack_asos_public_pilot_abx",
]
