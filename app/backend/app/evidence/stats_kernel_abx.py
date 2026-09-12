from __future__ import annotations

import math
import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Final, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_serializer,
    field_validator,
    model_validator,
)

from app.backend.app.evidence._common import canonical_digest
from app.backend.app.evidence.abx import (
    ABX_VERSION,
    AbxError,
    validate_abx_document,
)
from app.backend.app.evidence.stats_kernel import (
    AnalysisPlan,
    GitCommit,
    OpaqueId,
    Sha256Digest,
    StatsKernelBuild,
    StatsKernelNumericTolerances,
    StatsKernelResult,
)

ESTIMATE_SCHEMA_ID: Final = "urn:evidenceos:abx:schema:0.1:estimate"
METHOD_PROFILE_SCHEMA_ID: Final = (
    "urn:evidenceos:abx:schema:0.1:method-profile"
)
STATS_KERNEL_ABX_EXTENSION: Final = "trialmark.stats-kernel"
STATS_KERNEL_ABX_MATERIALIZER_VERSION: Final = "0.1.0"
METHOD_PROFILE_LAST_VERIFIED_COMMIT: Final = (
    "5c65c0d309427d8a5c41536889daa790b982e7e1"
)

_MAX_SAFE_INTEGER = 9_007_199_254_740_991
_UTC_TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z$"
)
ProbabilityString = Annotated[
    str,
    StringConstraints(pattern=r"^(?:0(?:\.[0-9]+)?|1(?:\.0+)?)$"),
]
SafeCount = Annotated[int, Field(strict=True, ge=0, le=_MAX_SAFE_INTEGER)]


class StatsKernelAbxMaterializationError(ValueError):
    """Raised when a StatsKernel result cannot become an honest ABX estimate."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
        hide_input_in_errors=True,
    )


class StatsKernelAbxEstimateContext(_FrozenModel):
    """Caller-owned run identity and clock values absent from StatsKernelResult."""

    estimate_id: OpaqueId
    run_id: OpaqueId
    estimand_id: OpaqueId
    baseline_intervention_id: OpaqueId
    comparison_intervention_id: OpaqueId
    produced_at: str

    @field_validator("produced_at")
    @classmethod
    def validate_produced_at(cls, value: str) -> str:
        if _UTC_TIMESTAMP_PATTERN.fullmatch(value) is None:
            raise ValueError("produced_at must be a canonical UTC timestamp ending in Z")
        try:
            datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as error:
            raise ValueError("produced_at must be a valid UTC timestamp") from error
        return value

    @model_validator(mode="after")
    def validate_contrast(self) -> Self:
        if self.baseline_intervention_id == self.comparison_intervention_id:
            raise ValueError("ABX contrast must use different intervention IDs")
        return self


class _AbxEstimateContrast(_FrozenModel):
    baseline_intervention_id: OpaqueId
    comparison_intervention_id: OpaqueId


class _AbxEstimateUncertainty(_FrozenModel):
    kind: Literal["confidence_interval"] = "confidence_interval"
    level: ProbabilityString
    lower: float
    upper: float
    p_value: float = Field(strict=True, ge=0.0, le=1.0)


class _AbxGroupSampleSize(_FrozenModel):
    intervention_id: OpaqueId
    users: SafeCount


class _AbxEstimateSampleSize(_FrozenModel):
    total: SafeCount
    groups: tuple[_AbxGroupSampleSize, _AbxGroupSampleSize]

    @model_validator(mode="after")
    def validate_groups(self) -> Self:
        if self.groups[0].intervention_id == self.groups[1].intervention_id:
            raise ValueError("sample-size groups must use different intervention IDs")
        if self.total != sum(group.users for group in self.groups):
            raise ValueError("sample-size total must equal the group sizes")
        return self

    @field_serializer("groups", when_used="json")
    def serialize_groups(
        self,
        groups: tuple[_AbxGroupSampleSize, _AbxGroupSampleSize],
    ) -> dict[str, int]:
        return {group.intervention_id: group.users for group in groups}


class _AbxMetricLineage(_FrozenModel):
    metric_id: OpaqueId
    metric_version: str = Field(min_length=1, max_length=64)
    metric_digest: Sha256Digest


class _AbxRunnerLineage(_FrozenModel):
    name: OpaqueId
    version: str = Field(min_length=1, max_length=64)
    build_digest: Sha256Digest
    dependency_lock_digest: Sha256Digest
    analyzer_version: str = Field(min_length=1, max_length=64)
    policy_version: str = Field(min_length=1, max_length=64)


class _AbxEstimateLineage(_FrozenModel):
    protocol_revision_id: Sha256Digest
    metric: _AbxMetricLineage
    query_ids: tuple[Sha256Digest, ...] = Field(min_length=1)
    source_snapshot_ids: tuple[OpaqueId, ...] = Field(min_length=1)
    runner: _AbxRunnerLineage

    @model_validator(mode="after")
    def validate_unique_references(self) -> Self:
        if len(set(self.query_ids)) != len(self.query_ids):
            raise ValueError("query IDs must be unique")
        if len(set(self.source_snapshot_ids)) != len(self.source_snapshot_ids):
            raise ValueError("source snapshot IDs must be unique")
        return self


class _StatsKernelArmRate(_FrozenModel):
    intervention_id: OpaqueId
    rate: float = Field(strict=True, ge=0.0, le=1.0)


class _StatsKernelArmRates(_FrozenModel):
    baseline: _StatsKernelArmRate
    comparison: _StatsKernelArmRate


class _StatsKernelDiagnosticsExtension(_FrozenModel):
    test_statistic: float
    is_significant: bool
    power_achieved: float = Field(strict=True, ge=0.0, le=1.0)


class _StatsKernelExtension(_FrozenModel):
    materializer_version: Literal["0.1.0"]
    adapter_version: Literal["0.1.0"]
    git_commit: GitCommit
    numeric_tolerances: StatsKernelNumericTolerances
    random_seed: None
    analysis_plan_digest: Sha256Digest
    input_aggregate_digests: tuple[Sha256Digest, Sha256Digest]
    output_estimate_digest: Sha256Digest
    output_diagnostics_digest: Sha256Digest
    arm_rates: _StatsKernelArmRates
    diagnostics: _StatsKernelDiagnosticsExtension


class _StatsKernelAbxEstimateCore(_FrozenModel):
    schema_version: Literal["0.1.0"] = "0.1.0"
    estimate_id: OpaqueId
    run_id: OpaqueId
    estimand_id: OpaqueId
    contrast: _AbxEstimateContrast
    effect_measure: Literal["risk_difference"] = "risk_difference"
    point_estimate: float
    uncertainty: _AbxEstimateUncertainty
    sample_size: _AbxEstimateSampleSize
    lineage: _AbxEstimateLineage
    produced_at: str
    extensions: _StatsKernelExtension

    @field_serializer("extensions", when_used="json")
    def serialize_extensions(
        self,
        extension: _StatsKernelExtension,
    ) -> dict[str, object]:
        return {STATS_KERNEL_ABX_EXTENSION: extension.model_dump(mode="json")}


class StatsKernelAbxEstimate(_StatsKernelAbxEstimateCore):
    """Typed, schema-valid ABX v0.1 estimate produced from StatsKernelResult."""

    content_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_content_digest(self) -> Self:
        digest_core = self.model_dump(mode="json", exclude={"content_digest"})
        if self.content_digest != _digest(digest_core):
            raise ValueError("content digest mismatch")
        return self


class _MethodErrorControl(_FrozenModel):
    fixed_horizon: Literal[True] = True
    nominal_alpha: float = Field(strict=True, ge=0.001, le=0.1)
    sidedness: Literal["two_sided"] = "two_sided"


class _MethodAsymptotics(_FrozenModel):
    min_n_per_arm: Literal[30] = 30
    min_expected_count: Literal[5] = 5


class _MethodRounding(_FrozenModel):
    risk_difference_decimal_places: Literal[6] = 6
    p_value_decimal_places: Literal[6] = 6
    test_statistic_decimal_places: Literal[4] = 4


class _MethodReferenceImplementation(_FrozenModel):
    package: Literal["statsmodels"] = "statsmodels"
    version: Literal["0.14.6"] = "0.14.6"
    test: Literal["statsmodels.stats.proportion.proportions_ztest"] = (
        "statsmodels.stats.proportion.proportions_ztest"
    )
    interval: Literal[
        "statsmodels.stats.proportion.confint_proportions_2indep(method='newcomb')"
    ] = "statsmodels.stats.proportion.confint_proportions_2indep(method='newcomb')"


class _MethodObservedMaxDeviation(_FrozenModel):
    test_statistic: float = Field(
        default=4.06056221140538e-05,
        strict=True,
        ge=0.0,
    )
    p_value: float = Field(
        default=4.50466474712086e-07,
        strict=True,
        ge=0.0,
    )
    confidence_interval: float = Field(
        default=4.85022202845187e-07,
        strict=True,
        ge=0.0,
    )


class _MethodNumericContract(_FrozenModel):
    rounding: _MethodRounding = Field(default_factory=_MethodRounding)
    reference_implementation: _MethodReferenceImplementation = Field(
        default_factory=_MethodReferenceImplementation
    )
    observed_max_deviation: _MethodObservedMaxDeviation = Field(
        default_factory=_MethodObservedMaxDeviation
    )


class _MethodDeterminism(_FrozenModel):
    closed_form: Literal[True] = True


class _MethodAssumptions(_FrozenModel):
    equal_allocation: Literal[False] = False


class _MethodVerificationEvidence(_FrozenModel):
    oracle_case_ids: tuple[Literal["binary_pooled_z_newcombe"], ...] = Field(
        default=("binary_pooled_z_newcombe",),
        min_length=1,
    )
    last_verified_commit: Literal[
        "5c65c0d309427d8a5c41536889daa790b982e7e1"
    ] = METHOD_PROFILE_LAST_VERIFIED_COMMIT


class MethodGuaranteeProfile(_FrozenModel):
    """Machine-readable guarantees for the sole supported analysis method."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    method_id: Literal["binary_pooled_z_newcombe"] = "binary_pooled_z_newcombe"
    method_version: Literal["binary_pooled_z_newcombe_v1"] = (
        "binary_pooled_z_newcombe_v1"
    )
    implementation_digest: Sha256Digest
    test_estimand: Literal["risk_difference"] = "risk_difference"
    interval_estimand: Literal["risk_difference"] = "risk_difference"
    error_control: _MethodErrorControl
    asymptotics: _MethodAsymptotics = Field(default_factory=_MethodAsymptotics)
    numeric_contract: _MethodNumericContract = Field(
        default_factory=_MethodNumericContract
    )
    determinism: _MethodDeterminism = Field(default_factory=_MethodDeterminism)
    assumptions: _MethodAssumptions = Field(default_factory=_MethodAssumptions)
    verification_evidence: _MethodVerificationEvidence = Field(
        default_factory=_MethodVerificationEvidence
    )


def _digest(value: object) -> str:
    return canonical_digest(value)


def _probability_string(value: float) -> str:
    text = format(Decimal(str(value)).normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _assert_result_digests(result: StatsKernelResult) -> None:
    estimate_digest = _digest(result.estimate.model_dump(mode="json"))
    if estimate_digest != result.lineage.output_estimate_digest:
        raise StatsKernelAbxMaterializationError(
            "StatsKernel estimate digest mismatch"
        )
    diagnostics_digest = _digest(result.diagnostics.model_dump(mode="json"))
    if diagnostics_digest != result.lineage.output_diagnostics_digest:
        raise StatsKernelAbxMaterializationError(
            "StatsKernel diagnostics digest mismatch"
        )


def _validated_result(result: StatsKernelResult) -> StatsKernelResult:
    try:
        validated = StatsKernelResult.model_validate(result.model_dump(mode="python"))
    except ValidationError as error:
        raise StatsKernelAbxMaterializationError(
            "StatsKernel result failed strict validation"
        ) from error

    _assert_result_digests(validated)
    if len(set(validated.lineage.input_aggregate_digests)) != 2:
        raise StatsKernelAbxMaterializationError(
            "StatsKernel input aggregate digests must be distinct"
        )

    estimate = validated.estimate
    diagnostics = validated.diagnostics
    tolerances = validated.lineage.numeric_tolerances
    uncertainty = estimate.uncertainty
    expected_effect = estimate.treatment_rate - estimate.control_rate
    if not math.isclose(
        estimate.point_estimate,
        expected_effect,
        rel_tol=0.0,
        abs_tol=3.0 * tolerances.point_estimate,
    ):
        raise StatsKernelAbxMaterializationError(
            "StatsKernel point estimate does not match arm rates"
        )
    if (
        uncertainty.lower < -1.0 - tolerances.confidence_interval
        or uncertainty.upper > 1.0 + tolerances.confidence_interval
    ):
        raise StatsKernelAbxMaterializationError(
            "StatsKernel confidence interval bounds exceed the risk-difference domain"
        )
    if not (
        uncertainty.lower - tolerances.confidence_interval
        <= estimate.point_estimate
        <= uncertainty.upper + tolerances.confidence_interval
    ):
        raise StatsKernelAbxMaterializationError(
            "StatsKernel point estimate falls outside its confidence interval"
        )
    alpha = 1.0 - uncertainty.level
    if (
        alpha < 0.001 - tolerances.ci_level
        or alpha > 0.1 + tolerances.ci_level
    ):
        raise StatsKernelAbxMaterializationError(
            "StatsKernel confidence level is unsupported"
        )
    expected_significance = uncertainty.p_value < alpha
    if (
        abs(uncertainty.p_value - alpha)
        > tolerances.p_value + tolerances.ci_level
        and diagnostics.is_significant is not expected_significance
    ):
        raise StatsKernelAbxMaterializationError(
            "StatsKernel significance does not match p-value"
        )
    return validated


def materialize_method_guarantee_profile(
    build: StatsKernelBuild,
    plan: AnalysisPlan,
) -> MethodGuaranteeProfile:
    """Bind the supported method contract to one build and frozen plan alpha."""

    try:
        validated_build = StatsKernelBuild.model_validate(
            build.model_dump(mode="python")
        )
        validated_plan = AnalysisPlan.model_validate(plan.model_dump(mode="python"))
        profile = MethodGuaranteeProfile(
            implementation_digest=validated_build.build_digest,
            error_control=_MethodErrorControl(nominal_alpha=validated_plan.alpha),
        )
        validate_abx_document(
            profile.model_dump(mode="json"),
            METHOD_PROFILE_SCHEMA_ID,
        )
    except (AbxError, ValidationError) as error:
        raise StatsKernelAbxMaterializationError(
            "StatsKernel method guarantee profile materialization failed"
        ) from error
    return profile


def materialize_stats_kernel_abx_estimate(
    result: StatsKernelResult,
    context: StatsKernelAbxEstimateContext,
) -> StatsKernelAbxEstimate:
    """Materialize one deterministic ABX estimate without inventing run state."""

    try:
        result = _validated_result(result)
        baseline_group, comparison_group = result.estimate.sample_size.groups
        if (
            baseline_group.intervention_id != context.baseline_intervention_id
            or comparison_group.intervention_id
            != context.comparison_intervention_id
        ):
            raise StatsKernelAbxMaterializationError(
                "ABX contrast mismatch with StatsKernel sample groups"
            )
        input_lineage = result.lineage.input_lineage
        core = _StatsKernelAbxEstimateCore(
            estimate_id=context.estimate_id,
            run_id=context.run_id,
            estimand_id=context.estimand_id,
            contrast=_AbxEstimateContrast(
                baseline_intervention_id=context.baseline_intervention_id,
                comparison_intervention_id=context.comparison_intervention_id,
            ),
            point_estimate=result.estimate.point_estimate,
            uncertainty=_AbxEstimateUncertainty(
                level=_probability_string(result.estimate.uncertainty.level),
                lower=result.estimate.uncertainty.lower,
                upper=result.estimate.uncertainty.upper,
                p_value=result.estimate.uncertainty.p_value,
            ),
            sample_size=_AbxEstimateSampleSize(
                total=result.estimate.sample_size.total,
                groups=(
                    _AbxGroupSampleSize(
                        intervention_id=baseline_group.intervention_id,
                        users=baseline_group.users,
                    ),
                    _AbxGroupSampleSize(
                        intervention_id=comparison_group.intervention_id,
                        users=comparison_group.users,
                    ),
                ),
            ),
            lineage=_AbxEstimateLineage(
                protocol_revision_id=input_lineage.protocol_revision_id,
                metric=_AbxMetricLineage(
                    metric_id=input_lineage.metric_id,
                    metric_version=input_lineage.metric_version,
                    metric_digest=input_lineage.metric_digest,
                ),
                query_ids=input_lineage.query_ids,
                source_snapshot_ids=input_lineage.source_snapshot_ids,
                runner=_AbxRunnerLineage(
                    name=result.lineage.kernel_name,
                    version=result.lineage.kernel_version,
                    build_digest=result.lineage.build_digest,
                    dependency_lock_digest=result.lineage.dependency_lock_digest,
                    analyzer_version=result.lineage.analyzer_version,
                    policy_version=result.lineage.policy_version,
                ),
            ),
            produced_at=context.produced_at,
            extensions=_StatsKernelExtension(
                materializer_version=STATS_KERNEL_ABX_MATERIALIZER_VERSION,
                adapter_version=result.lineage.adapter_version,
                git_commit=result.lineage.git_commit,
                numeric_tolerances=result.lineage.numeric_tolerances,
                random_seed=result.lineage.random_seed,
                analysis_plan_digest=result.lineage.analysis_plan_digest,
                input_aggregate_digests=result.lineage.input_aggregate_digests,
                output_estimate_digest=result.lineage.output_estimate_digest,
                output_diagnostics_digest=result.lineage.output_diagnostics_digest,
                arm_rates=_StatsKernelArmRates(
                    baseline=_StatsKernelArmRate(
                        intervention_id=context.baseline_intervention_id,
                        rate=result.estimate.control_rate,
                    ),
                    comparison=_StatsKernelArmRate(
                        intervention_id=context.comparison_intervention_id,
                        rate=result.estimate.treatment_rate,
                    ),
                ),
                diagnostics=_StatsKernelDiagnosticsExtension(
                    test_statistic=result.diagnostics.test_statistic,
                    is_significant=result.diagnostics.is_significant,
                    power_achieved=result.diagnostics.power_achieved,
                ),
            ),
        )
        core_document = core.model_dump(mode="json")
        estimate = StatsKernelAbxEstimate(
            **core.model_dump(mode="python"),
            content_digest=_digest(core_document),
        )
        validate_abx_document(estimate.model_dump(mode="json"), ESTIMATE_SCHEMA_ID)
    except StatsKernelAbxMaterializationError:
        raise
    except (AbxError, ValidationError) as error:
        raise StatsKernelAbxMaterializationError(
            "StatsKernel result failed ABX estimate materialization"
        ) from error

    if estimate.schema_version != ABX_VERSION:
        raise StatsKernelAbxMaterializationError("ABX schema version mismatch")
    return estimate
