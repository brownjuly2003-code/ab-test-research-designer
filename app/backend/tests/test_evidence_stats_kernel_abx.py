from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from app.backend.app.evidence.abx import canonical_json_bytes, validate_abx_document
from app.backend.app.evidence.stats_kernel import (
    STATS_KERNEL_SOURCE_PATHS,
    AnalysisPlan,
    BinaryArmStatistics,
    BinarySufficientStatistics,
    LegacyStatsKernelAdapter,
    StatsKernelBuild,
    StatsKernelInputLineage,
    StatsKernelRequest,
    StatsKernelResult,
)
from app.backend.app.evidence.stats_kernel_abx import (
    ESTIMATE_SCHEMA_ID,
    METHOD_PROFILE_SCHEMA_ID,
    STATS_KERNEL_ABX_EXTENSION,
    StatsKernelAbxEstimate,
    StatsKernelAbxEstimateContext,
    StatsKernelAbxMaterializationError,
    materialize_method_guarantee_profile,
    materialize_stats_kernel_abx_estimate,
)


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _result(
    *,
    control_conversions: int = 100,
    control_users: int = 1000,
    treatment_conversions: int = 130,
    treatment_users: int = 1000,
) -> StatsKernelResult:
    build = StatsKernelBuild(
        git_commit="a" * 40,
        build_digest="sha256:" + "b" * 64,
        dependency_lock_digest="sha256:" + "c" * 64,
    )
    request = StatsKernelRequest(
        plan=AnalysisPlan(alpha=0.05),
        aggregates=BinarySufficientStatistics(
            control=BinaryArmStatistics(
                intervention_id="control",
                conversions=control_conversions,
                users=control_users,
            ),
            treatment=BinaryArmStatistics(
                intervention_id="treatment",
                conversions=treatment_conversions,
                users=treatment_users,
            ),
        ),
        lineage=StatsKernelInputLineage(
            protocol_revision_id="sha256:" + "1" * 64,
            metric_id="metric_checkout_conversion",
            metric_version="v1",
            metric_digest="sha256:" + "2" * 64,
            query_ids=("sha256:" + "3" * 64,),
            source_snapshot_ids=("source_checkout_aggregate_v1",),
        ),
    )
    return LegacyStatsKernelAdapter(build).analyze(request)


def _context() -> StatsKernelAbxEstimateContext:
    return StatsKernelAbxEstimateContext(
        estimate_id="estimate_checkout_conversion",
        run_id="run_checkout_conversion",
        estimand_id="estimand_checkout_conversion_itt",
        baseline_intervention_id="control",
        comparison_intervention_id="treatment",
        produced_at="2026-08-23T14:30:00.123Z",
    )


def test_materializer_emits_deterministic_schema_valid_method_profile() -> None:
    build = StatsKernelBuild(
        git_commit="a" * 40,
        build_digest="sha256:" + "b" * 64,
        dependency_lock_digest="sha256:" + "c" * 64,
    )
    plan = AnalysisPlan(alpha=0.025)

    first = materialize_method_guarantee_profile(build, plan)
    second = materialize_method_guarantee_profile(build, plan)
    document = first.model_dump(mode="json")

    assert second == first
    validate_abx_document(document, METHOD_PROFILE_SCHEMA_ID)
    assert document == {
        "schema_version": "0.1.0",
        "method_id": "binary_pooled_z_newcombe",
        "method_version": "binary_pooled_z_newcombe_v1",
        "implementation_digest": build.build_digest,
        "test_estimand": "risk_difference",
        "interval_estimand": "risk_difference",
        "error_control": {
            "fixed_horizon": True,
            "nominal_alpha": 0.025,
            "sidedness": "two_sided",
        },
        "asymptotics": {"min_n_per_arm": 30, "min_expected_count": 5},
        "numeric_contract": {
            "rounding": {
                "risk_difference_decimal_places": 6,
                "p_value_decimal_places": 6,
                "test_statistic_decimal_places": 4,
            },
            "reference_implementation": {
                "package": "statsmodels",
                "version": "0.14.6",
                "test": "statsmodels.stats.proportion.proportions_ztest",
                "interval": (
                    "statsmodels.stats.proportion."
                    "confint_proportions_2indep(method='newcomb')"
                ),
            },
            "observed_max_deviation": {
                "test_statistic": 4.06056221140538e-05,
                "p_value": 4.50466474712086e-07,
                "confidence_interval": 4.85022202845187e-07,
            },
        },
        "determinism": {"closed_form": True},
        "assumptions": {"equal_allocation": False},
        "verification_evidence": {
            "oracle_case_ids": ["binary_pooled_z_newcombe"],
            "last_verified_commit": (
                "5c65c0d309427d8a5c41536889daa790b982e7e1"
            ),
        },
    }


def test_materializer_emits_deterministic_schema_valid_estimate() -> None:
    result = _result()

    first = materialize_stats_kernel_abx_estimate(result, _context())
    second = materialize_stats_kernel_abx_estimate(result, _context())
    document = first.model_dump(mode="json")

    assert second == first
    validate_abx_document(document, ESTIMATE_SCHEMA_ID)
    assert document["schema_version"] == "0.1.0"
    assert document["estimate_id"] == "estimate_checkout_conversion"
    assert document["run_id"] == "run_checkout_conversion"
    assert document["estimand_id"] == "estimand_checkout_conversion_itt"
    assert document["contrast"] == {
        "baseline_intervention_id": "control",
        "comparison_intervention_id": "treatment",
    }
    assert document["effect_measure"] == "risk_difference"
    assert document["point_estimate"] == result.estimate.point_estimate
    assert document["uncertainty"] == {
        "kind": "confidence_interval",
        "level": "0.95",
        "lower": result.estimate.uncertainty.lower,
        "upper": result.estimate.uncertainty.upper,
        "p_value": result.estimate.uncertainty.p_value,
    }
    assert document["sample_size"] == {
        "total": 2000,
        "groups": {"control": 1000, "treatment": 1000},
    }
    assert document["lineage"] == {
        "protocol_revision_id": "sha256:" + "1" * 64,
        "metric": {
            "metric_id": "metric_checkout_conversion",
            "metric_version": "v1",
            "metric_digest": "sha256:" + "2" * 64,
        },
        "query_ids": ["sha256:" + "3" * 64],
        "source_snapshot_ids": ["source_checkout_aggregate_v1"],
        "runner": {
            "name": "legacy_stats_kernel",
            "version": "0.1.0",
            "build_digest": "sha256:" + "b" * 64,
            "dependency_lock_digest": "sha256:" + "c" * 64,
            "analyzer_version": "binary_pooled_z_newcombe_v1",
            "policy_version": "fixed_horizon_two_sided_v1",
        },
    }
    assert document["produced_at"] == "2026-08-23T14:30:00.123Z"
    assert document["extensions"] == {
        STATS_KERNEL_ABX_EXTENSION: {
            "adapter_version": "0.1.0",
            "analysis_plan_digest": result.lineage.analysis_plan_digest,
            "arm_rates": {
                "baseline": {"intervention_id": "control", "rate": 0.1},
                "comparison": {"intervention_id": "treatment", "rate": 0.13},
            },
            "diagnostics": result.diagnostics.model_dump(mode="json"),
            "git_commit": "a" * 40,
            "input_aggregate_digests": list(
                result.lineage.input_aggregate_digests
            ),
            "materializer_version": "0.1.0",
            "numeric_tolerances": result.lineage.numeric_tolerances.model_dump(
                mode="json"
            ),
            "output_diagnostics_digest": result.lineage.output_diagnostics_digest,
            "output_estimate_digest": result.lineage.output_estimate_digest,
            "random_seed": None,
        }
    }
    digest_core = {
        key: value for key, value in document.items() if key != "content_digest"
    }
    assert document["content_digest"] == _digest(digest_core)
    assert "random_seed" not in document["lineage"]["runner"]
    assert "app/evidence/stats_kernel_abx.py" in STATS_KERNEL_SOURCE_PATHS

    changed_timestamp = _context().model_copy(
        update={"produced_at": "2026-08-23T14:30:00.124Z"}
    )
    changed = materialize_stats_kernel_abx_estimate(result, changed_timestamp)
    assert changed.content_digest != first.content_digest


def test_materialized_estimate_is_deeply_immutable_and_validates_digest() -> None:
    estimate = materialize_stats_kernel_abx_estimate(_result(), _context())
    document_before = estimate.model_dump(mode="json")

    assert isinstance(estimate.sample_size.groups, tuple)
    with pytest.raises(ValidationError, match="frozen"):
        estimate.sample_size.groups[0].users = 0
    assert not isinstance(estimate.extensions, dict)
    with pytest.raises(ValidationError, match="frozen"):
        estimate.extensions.git_commit = "d" * 40

    invalid_payload = estimate.model_dump(mode="python")
    invalid_payload["content_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError, match="content digest mismatch"):
        StatsKernelAbxEstimate.model_validate(invalid_payload)
    assert estimate.model_dump(mode="json") == document_before


@pytest.mark.parametrize(
    "produced_at",
    [
        "2026-08-23T14:30:00+00:00",
        "2026-08-23T10:30:00-04:00",
        "2026-02-30T14:30:00Z",
        "2026-08-23 14:30:00Z",
    ],
)
def test_context_rejects_noncanonical_utc_timestamps(produced_at: str) -> None:
    with pytest.raises(ValidationError, match="produced_at"):
        StatsKernelAbxEstimateContext(
            estimate_id="estimate_checkout_conversion",
            run_id="run_checkout_conversion",
            estimand_id="estimand_checkout_conversion_itt",
            baseline_intervention_id="control",
            comparison_intervention_id="treatment",
            produced_at=produced_at,
        )


def test_context_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        StatsKernelAbxEstimateContext.model_validate(
            {
                "estimate_id": "estimate_checkout_conversion",
                "run_id": "run_checkout_conversion",
                "estimand_id": "estimand_checkout_conversion_itt",
                "baseline_intervention_id": "control",
                "comparison_intervention_id": "treatment",
                "produced_at": "2026-08-23T14:30:00Z",
                "raw_rows": [],
            }
        )


@pytest.mark.parametrize(
    ("lineage_field", "error_match"),
    [
        ("output_estimate_digest", "estimate digest mismatch"),
        ("output_diagnostics_digest", "diagnostics digest mismatch"),
    ],
)
def test_materializer_fails_closed_on_result_digest_mismatch(
    lineage_field: str,
    error_match: str,
) -> None:
    result = _result()
    bad_lineage = result.lineage.model_copy(
        update={lineage_field: "sha256:" + "0" * 64}
    )
    inconsistent_result = result.model_copy(update={"lineage": bad_lineage})

    with pytest.raises(StatsKernelAbxMaterializationError, match=error_match):
        materialize_stats_kernel_abx_estimate(inconsistent_result, _context())


def test_materializer_rejects_contrast_group_mismatch() -> None:
    mismatched_context = _context().model_copy(
        update={"comparison_intervention_id": "other_treatment"}
    )

    with pytest.raises(StatsKernelAbxMaterializationError, match="contrast mismatch"):
        materialize_stats_kernel_abx_estimate(_result(), mismatched_context)


def test_materializer_rejects_semantically_inconsistent_estimate() -> None:
    result = _result()
    inconsistent_estimate = result.estimate.model_copy(update={"point_estimate": 0.5})
    matching_lineage = result.lineage.model_copy(
        update={
            "output_estimate_digest": _digest(
                inconsistent_estimate.model_dump(mode="json")
            )
        }
    )
    inconsistent_result = result.model_copy(
        update={"estimate": inconsistent_estimate, "lineage": matching_lineage}
    )

    with pytest.raises(
        StatsKernelAbxMaterializationError,
        match="point estimate does not match arm rates",
    ):
        materialize_stats_kernel_abx_estimate(inconsistent_result, _context())


def test_materializer_rejects_semantically_inconsistent_diagnostics() -> None:
    result = _result()
    inconsistent_diagnostics = result.diagnostics.model_copy(
        update={"is_significant": False}
    )
    matching_lineage = result.lineage.model_copy(
        update={
            "output_diagnostics_digest": _digest(
                inconsistent_diagnostics.model_dump(mode="json")
            )
        }
    )
    inconsistent_result = result.model_copy(
        update={
            "diagnostics": inconsistent_diagnostics,
            "lineage": matching_lineage,
        }
    )

    with pytest.raises(
        StatsKernelAbxMaterializationError,
        match="significance does not match p-value",
    ):
        materialize_stats_kernel_abx_estimate(inconsistent_result, _context())


@pytest.mark.parametrize(
    ("uncertainty_update", "error_match"),
    [
        ({"lower": -2.0, "upper": 0.1}, "confidence interval bounds"),
        ({"level": 0.5}, "confidence level is unsupported"),
    ],
)
def test_materializer_rejects_values_outside_supported_analysis_domain(
    uncertainty_update: dict[str, float],
    error_match: str,
) -> None:
    result = _result()
    inconsistent_uncertainty = result.estimate.uncertainty.model_copy(
        update=uncertainty_update
    )
    inconsistent_estimate = result.estimate.model_copy(
        update={"uncertainty": inconsistent_uncertainty}
    )
    matching_lineage = result.lineage.model_copy(
        update={
            "output_estimate_digest": _digest(
                inconsistent_estimate.model_dump(mode="json")
            )
        }
    )
    inconsistent_result = result.model_copy(
        update={"estimate": inconsistent_estimate, "lineage": matching_lineage}
    )

    with pytest.raises(StatsKernelAbxMaterializationError, match=error_match):
        materialize_stats_kernel_abx_estimate(inconsistent_result, _context())


def test_materializer_rejects_duplicate_input_aggregate_digests() -> None:
    result = _result()
    duplicate = result.lineage.input_aggregate_digests[0]
    inconsistent_lineage = result.lineage.model_copy(
        update={"input_aggregate_digests": (duplicate, duplicate)}
    )
    inconsistent_result = result.model_copy(update={"lineage": inconsistent_lineage})

    with pytest.raises(
        StatsKernelAbxMaterializationError,
        match="aggregate digests must be distinct",
    ):
        materialize_stats_kernel_abx_estimate(inconsistent_result, _context())


def test_materializer_allows_independent_legacy_rounding() -> None:
    result = _result(
        control_conversions=27,
        control_users=29,
        treatment_conversions=9,
        treatment_users=29,
    )

    estimate = materialize_stats_kernel_abx_estimate(result, _context())

    assert estimate.point_estimate == result.estimate.point_estimate


def test_materializer_allows_significance_within_rounded_threshold_tolerance() -> None:
    result = _result()
    rounded_uncertainty = result.estimate.uncertainty.model_copy(
        update={"p_value": 0.04997}
    )
    rounded_estimate = result.estimate.model_copy(
        update={"uncertainty": rounded_uncertainty}
    )
    rounded_diagnostics = result.diagnostics.model_copy(
        update={"is_significant": False}
    )
    matching_lineage = result.lineage.model_copy(
        update={
            "output_estimate_digest": _digest(
                rounded_estimate.model_dump(mode="json")
            ),
            "output_diagnostics_digest": _digest(
                rounded_diagnostics.model_dump(mode="json")
            ),
        }
    )
    rounded_result = result.model_copy(
        update={
            "estimate": rounded_estimate,
            "diagnostics": rounded_diagnostics,
            "lineage": matching_lineage,
        }
    )

    estimate = materialize_stats_kernel_abx_estimate(rounded_result, _context())

    assert estimate.uncertainty.p_value == 0.04997
