from __future__ import annotations

import math
import subprocess
from functools import lru_cache
from pathlib import Path
from statistics import NormalDist
from typing import Annotated, Final, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.backend.app.evidence._common import (
    SHA256_PATTERN as _SHA256_PATTERN,
)
from app.backend.app.evidence._common import (
    canonical_digest,
    sha256_hex,
)
from app.backend.app.evidence.abx import canonical_json_bytes, load_abx_document
from app.backend.app.schemas.api import (
    ObservedResultsBinary,
    ResultsRequest,
    ResultsResponse,
)
from app.backend.app.services.results_service import analyze_results
from app.backend.app.stats.binary import (
    newcombe_difference_interval,
    standard_normal_sf,
)

STATS_KERNEL_VERSION: Final = "0.1.0"
STATS_KERNEL_ADAPTER_VERSION: Final = "0.1.0"
BINARY_ANALYZER_VERSION: Final = "binary_pooled_z_newcombe_v1"
BINARY_POLICY_VERSION: Final = "fixed_horizon_two_sided_v1"
STATS_KERNEL_BUILD_INFO_PATH: Final = "BUILD_INFO.json"
ABX_SCHEMA_SOURCE_PATHS: Final = (
    "app/evidence/contracts/schemas/abx/0.1/amendments.schema.json",
    "app/evidence/contracts/schemas/abx/0.1/common.schema.json",
    "app/evidence/contracts/schemas/abx/0.1/decision-statement.schema.json",
    "app/evidence/contracts/schemas/abx/0.1/decision.schema.json",
    "app/evidence/contracts/schemas/abx/0.1/estimate.schema.json",
    "app/evidence/contracts/schemas/abx/0.1/finding.schema.json",
    "app/evidence/contracts/schemas/abx/0.1/manifest.schema.json",
    "app/evidence/contracts/schemas/abx/0.1/method-profile.schema.json",
    "app/evidence/contracts/schemas/abx/0.1/metric.schema.json",
    "app/evidence/contracts/schemas/abx/0.1/protocol.schema.json",
    "app/evidence/contracts/schemas/abx/0.1/run.schema.json",
    "app/evidence/contracts/schemas/abx/0.1/source.schema.json",
)
STATS_KERNEL_SOURCE_PATHS: Final = (
    # Every module of the abx package, listed one by one: a new module
    # that nobody adds here would silently leave the build identity
    # unchanged. test_build_identity_hashes_required_sources_lock_and_verified_commit
    # reads the directory and fails if this list drifts from it.
    "app/evidence/abx/__init__.py",
    "app/evidence/abx/_core.py",
    "app/evidence/abx/lineage.py",
    "app/evidence/abx/pack.py",
    "app/evidence/abx/privacy.py",
    "app/evidence/abx/verify.py",
    "app/evidence/abx/zip_safety.py",
    "app/evidence/stats_kernel.py",
    "app/evidence/stats_kernel_abx.py",
    *ABX_SCHEMA_SOURCE_PATHS,
    "app/schemas/api/__init__.py",
    "app/schemas/api/_results.py",
    "app/services/results_service.py",
    "app/services/results/__init__.py",
    "app/services/results/binary.py",
    "app/services/results/common.py",
    "app/services/results/dispatch.py",
    "app/stats/binary.py",
)

_MAX_SAFE_INTEGER = 9_007_199_254_740_991
_OPAQUE_ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$"
_GIT_COMMIT_PATTERN = r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$"

Sha256Digest = Annotated[str, StringConstraints(pattern=_SHA256_PATTERN)]
OpaqueId = Annotated[str, StringConstraints(pattern=_OPAQUE_ID_PATTERN)]
GitCommit = Annotated[str, StringConstraints(pattern=_GIT_COMMIT_PATTERN)]


class StatsKernelBuildError(RuntimeError):
    """Raised when reproducible kernel build identity cannot be established."""


class StatsKernelParityError(RuntimeError):
    """Raised when the legacy oracle violates the adapter's binary contract."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
        hide_input_in_errors=True,
    )


class StatsKernelNumericTolerances(_FrozenModel):
    point_estimate: float = Field(default=1e-6, strict=True, ge=1e-6, le=1e-6)
    confidence_interval: float = Field(default=1e-6, strict=True, ge=1e-6, le=1e-6)
    ci_level: float = Field(default=1e-4, strict=True, ge=1e-4, le=1e-4)
    p_value: float = Field(default=1e-6, strict=True, ge=1e-6, le=1e-6)
    test_statistic: float = Field(default=1e-4, strict=True, ge=1e-4, le=1e-4)
    power_achieved: float = Field(default=1e-3, strict=True, ge=1e-3, le=1e-3)


class AnalysisPlan(_FrozenModel):
    alpha: float = Field(strict=True, ge=0.001, le=0.1)
    schema_version: Literal["0.1.0"] = "0.1.0"
    method: Literal["binary_pooled_z_newcombe"] = "binary_pooled_z_newcombe"
    analyzer_version: Literal["binary_pooled_z_newcombe_v1"] = (
        BINARY_ANALYZER_VERSION
    )
    policy_version: Literal["fixed_horizon_two_sided_v1"] = BINARY_POLICY_VERSION
    effect_measure: Literal["risk_difference"] = "risk_difference"
    numeric_tolerances: StatsKernelNumericTolerances = Field(
        default_factory=StatsKernelNumericTolerances
    )
    random_seed: None = None


class BinaryArmStatistics(_FrozenModel):
    intervention_id: OpaqueId
    conversions: int = Field(strict=True, ge=0, le=_MAX_SAFE_INTEGER)
    users: int = Field(strict=True, ge=2, le=_MAX_SAFE_INTEGER)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.conversions > self.users:
            raise ValueError("conversions cannot exceed users")
        return self


class BinarySufficientStatistics(_FrozenModel):
    control: BinaryArmStatistics
    treatment: BinaryArmStatistics

    @model_validator(mode="after")
    def validate_interventions(self) -> Self:
        if self.control.intervention_id == self.treatment.intervention_id:
            raise ValueError("control and treatment must use different intervention IDs")
        return self


class StatsKernelInputLineage(_FrozenModel):
    protocol_revision_id: Sha256Digest
    metric_id: OpaqueId
    metric_version: str = Field(min_length=1, max_length=64)
    metric_digest: Sha256Digest
    query_ids: tuple[Sha256Digest, ...] = Field(min_length=1)
    source_snapshot_ids: tuple[OpaqueId, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_references(self) -> Self:
        if len(set(self.query_ids)) != len(self.query_ids):
            raise ValueError("query IDs must be unique")
        if len(set(self.source_snapshot_ids)) != len(self.source_snapshot_ids):
            raise ValueError("source snapshot IDs must be unique")
        return self


class StatsKernelRequest(_FrozenModel):
    plan: AnalysisPlan
    aggregates: BinarySufficientStatistics
    lineage: StatsKernelInputLineage


class StatsKernelBuild(_FrozenModel):
    kernel_version: Literal["0.1.0"] = STATS_KERNEL_VERSION
    git_commit: GitCommit
    build_digest: Sha256Digest
    dependency_lock_digest: Sha256Digest


class _StatsKernelBuildInfo(_FrozenModel):
    git_commit: GitCommit
    dirty: Literal[False]
    tracked_digest: Sha256Digest


class StatsKernelUncertainty(_FrozenModel):
    kind: Literal["confidence_interval"] = "confidence_interval"
    level: float = Field(strict=True, gt=0.0, lt=1.0)
    lower: float
    upper: float
    p_value: float = Field(strict=True, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if self.lower > self.upper:
            raise ValueError("confidence interval lower bound cannot exceed upper bound")
        return self


class StatsKernelGroupSampleSize(_FrozenModel):
    intervention_id: OpaqueId
    users: int = Field(strict=True, ge=2, le=_MAX_SAFE_INTEGER)


class StatsKernelSampleSize(_FrozenModel):
    total: int = Field(strict=True, ge=4, le=_MAX_SAFE_INTEGER)
    groups: tuple[StatsKernelGroupSampleSize, StatsKernelGroupSampleSize]

    @model_validator(mode="after")
    def validate_groups(self) -> Self:
        if self.groups[0].intervention_id == self.groups[1].intervention_id:
            raise ValueError("sample-size groups must use different intervention IDs")
        if self.total != self.groups[0].users + self.groups[1].users:
            raise ValueError("sample-size total must equal the group sizes")
        return self


class StatsKernelEstimate(_FrozenModel):
    effect_measure: Literal["risk_difference"] = "risk_difference"
    point_estimate: float = Field(strict=True, ge=-1.0, le=1.0)
    control_rate: float = Field(strict=True, ge=0.0, le=1.0)
    treatment_rate: float = Field(strict=True, ge=0.0, le=1.0)
    uncertainty: StatsKernelUncertainty
    sample_size: StatsKernelSampleSize


class StatsKernelDiagnostics(_FrozenModel):
    test_statistic: float
    is_significant: bool
    power_achieved: float = Field(strict=True, ge=0.0, le=1.0)


class StatsKernelLineage(_FrozenModel):
    kernel_name: Literal["legacy_stats_kernel"] = "legacy_stats_kernel"
    kernel_version: Literal["0.1.0"]
    adapter_version: Literal["0.1.0"] = STATS_KERNEL_ADAPTER_VERSION
    git_commit: GitCommit
    build_digest: Sha256Digest
    dependency_lock_digest: Sha256Digest
    analyzer_version: Literal["binary_pooled_z_newcombe_v1"]
    policy_version: Literal["fixed_horizon_two_sided_v1"]
    numeric_tolerances: StatsKernelNumericTolerances
    random_seed: None
    input_lineage: StatsKernelInputLineage
    analysis_plan_digest: Sha256Digest
    input_aggregate_digests: tuple[Sha256Digest, Sha256Digest]
    output_estimate_digest: Sha256Digest
    output_diagnostics_digest: Sha256Digest


class StatsKernelResult(_FrozenModel):
    estimate: StatsKernelEstimate
    diagnostics: StatsKernelDiagnostics
    lineage: StatsKernelLineage


class StatsKernel(Protocol):
    def analyze(self, request: StatsKernelRequest) -> StatsKernelResult:
        """Run one compiled plan against typed sufficient statistics."""


def _digest(value: object) -> str:
    return canonical_digest(value)


def _run_git(directory: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(directory), *arguments],
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="strict",
            text=True,
        )
    except (OSError, UnicodeError) as error:
        raise StatsKernelBuildError(
            "stats kernel Git provenance is unavailable"
        ) from error
    if completed.returncode != 0:
        raise StatsKernelBuildError("stats kernel Git provenance is unavailable")
    return completed.stdout.strip()


def _stats_kernel_source_records(root: Path) -> list[dict[str, str]]:
    return [
        {
            "path": relative_path,
            "digest": sha256_hex((root / relative_path).read_bytes()),
        }
        for relative_path in STATS_KERNEL_SOURCE_PATHS
    ]


def write_stats_kernel_build_info(*, backend_root: Path, git_commit: str) -> Path:
    """Write ``BUILD_INFO.json`` for a runtime that has no Git metadata.

    The stamp is canonical JSON with ``git_commit``, ``dirty=false``, and
    ``tracked_digest`` equal to the Git-path ``build_digest``.
    """
    try:
        root = backend_root.resolve(strict=True)
        build_info = _StatsKernelBuildInfo(
            git_commit=git_commit,
            dirty=False,
            tracked_digest=_digest(
                {"sources": _stats_kernel_source_records(root)}
            ),
        )
        target = root / STATS_KERNEL_BUILD_INFO_PATH
        target.write_bytes(
            canonical_json_bytes(build_info.model_dump(mode="json")) + b"\n"
        )
    except (OSError, UnicodeError, ValueError) as error:
        raise StatsKernelBuildError(
            "stats kernel build information could not be written"
        ) from error
    return target


def _load_stats_kernel_build_info(root: Path) -> StatsKernelBuild | None:
    try:
        payload = (root / STATS_KERNEL_BUILD_INFO_PATH).read_bytes()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise StatsKernelBuildError(
            "stats kernel build information is unavailable"
        ) from error

    try:
        build_info = _StatsKernelBuildInfo.model_validate(
            load_abx_document(payload, label=STATS_KERNEL_BUILD_INFO_PATH)
        )
        build_digest = _digest({"sources": _stats_kernel_source_records(root)})
        dependency_lock_digest = sha256_hex((root / "requirements.txt").read_bytes())
    except (OSError, UnicodeError, ValueError) as error:
        raise StatsKernelBuildError(
            "stats kernel build information is invalid"
        ) from error
    if build_digest != build_info.tracked_digest:
        raise StatsKernelBuildError(
            "stats kernel sources do not match the stamped build information"
        )
    return StatsKernelBuild(
        git_commit=build_info.git_commit,
        build_digest=build_digest,
        dependency_lock_digest=dependency_lock_digest,
    )


@lru_cache(maxsize=8)
def load_stats_kernel_build(
    *,
    backend_root: Path | None = None,
) -> StatsKernelBuild:
    """Resolve a fail-closed identity for the exact legacy kernel sources and lock.

    Prefers ``<backend_root>/BUILD_INFO.json``. The stamp is
    canonical JSON with exactly:

    - ``git_commit``: lowercase 40- or 64-character commit id
    - ``dirty``: ``false`` (any other value is rejected)
    - ``tracked_digest``: digest of ``{"sources": [...]}``, equal to the
      Git-path ``build_digest`` so bundle identities match between a clean
      checkout and a runtime image

    Git is only a development fallback when the stamp is absent. Missing
    both the stamp and a usable Git tree raises ``StatsKernelBuildError``.
    Resolved identities are cached in a bounded per-process LRU keyed by
    ``backend_root``, not for the whole process lifetime.
    """
    try:
        root = (
            backend_root.resolve(strict=True)
            if backend_root is not None
            else Path(__file__).resolve().parents[2]
        )
        stamped_build = _load_stats_kernel_build_info(root)
        if stamped_build is not None:
            return stamped_build
        try:
            repository_root = Path(
                _run_git(root, "rev-parse", "--show-toplevel")
            ).resolve(strict=True)
        except StatsKernelBuildError as error:
            raise StatsKernelBuildError(
                "stats kernel build identity is unavailable: "
                "BUILD_INFO.json is missing and Git fallback failed"
            ) from error
        backend_prefix = root.relative_to(repository_root)
        repository_paths = tuple(
            (backend_prefix / relative_path).as_posix()
            for relative_path in (*STATS_KERNEL_SOURCE_PATHS, "requirements.txt")
        )
        _run_git(
            repository_root,
            "ls-files",
            "--error-unmatch",
            "--",
            *repository_paths,
        )
        _run_git(repository_root, "diff", "--quiet", "HEAD", "--", *repository_paths)
        git_commit = _run_git(
            repository_root,
            "rev-parse",
            "--verify",
            "HEAD^{commit}",
        )
        source_records = _stats_kernel_source_records(root)
        dependency_lock_digest = sha256_hex((root / "requirements.txt").read_bytes())
        _run_git(repository_root, "diff", "--quiet", "HEAD", "--", *repository_paths)
    except StatsKernelBuildError:
        raise
    except (OSError, UnicodeError, ValueError) as error:
        raise StatsKernelBuildError(
            "stats kernel source, dependency lock, or Git provenance is unavailable"
        ) from error

    return StatsKernelBuild(
        git_commit=git_commit,
        build_digest=_digest({"sources": source_records}),
        dependency_lock_digest=dependency_lock_digest,
    )


def _aggregate_digest(
    role: Literal["control", "treatment"],
    aggregate: BinaryArmStatistics,
) -> str:
    return _digest(
        {
            "role": role,
            "intervention_id": aggregate.intervention_id,
            "conversions": aggregate.conversions,
            "users": aggregate.users,
        }
    )


def _assert_oracle_parity(
    oracle: ResultsResponse,
    request: StatsKernelRequest,
) -> None:
    tolerances = request.plan.numeric_tolerances
    control = request.aggregates.control
    treatment = request.aggregates.treatment
    expected_control_rate = control.conversions / control.users
    expected_treatment_rate = treatment.conversions / treatment.users
    expected_effect = expected_treatment_rate - expected_control_rate
    pooled_rate = (
        (control.conversions + treatment.conversions)
        / (control.users + treatment.users)
    )
    standard_error = math.sqrt(
        max(
            pooled_rate
            * (1.0 - pooled_rate)
            * ((1.0 / control.users) + (1.0 / treatment.users)),
            0.0,
        )
    )
    expected_ci_lower, expected_ci_upper = newcombe_difference_interval(
        treatment.conversions,
        treatment.users,
        control.conversions,
        control.users,
        request.plan.alpha,
    )
    if standard_error == 0.0:
        expected_p_value = 1.0
        expected_test_statistic = 0.0
        expected_power_achieved = 0.0
    else:
        expected_test_statistic = expected_effect / standard_error
        normal = NormalDist()
        expected_p_value = min(
            1.0,
            max(0.0, 2.0 * standard_normal_sf(abs(expected_test_statistic))),
        )
        z_critical = normal.inv_cdf(1.0 - request.plan.alpha / 2.0)
        expected_power_achieved = min(
            1.0,
            max(
                0.0,
                normal.cdf(abs(expected_test_statistic) - z_critical)
                + normal.cdf(-z_critical - abs(expected_test_statistic)),
            ),
        )
    numeric_contract = (
        math.isclose(
            oracle.control_rate / 100.0,  # type: ignore[operator]
            expected_control_rate,
            rel_tol=0.0,
            abs_tol=tolerances.point_estimate,
        )
        and math.isclose(
            oracle.treatment_rate / 100.0,  # type: ignore[operator]
            expected_treatment_rate,
            rel_tol=0.0,
            abs_tol=tolerances.point_estimate,
        )
        and math.isclose(
            oracle.observed_effect / 100.0,
            expected_effect,
            rel_tol=0.0,
            abs_tol=tolerances.point_estimate,
        )
        and math.isclose(
            oracle.ci_level,
            1.0 - request.plan.alpha,
            rel_tol=0.0,
            abs_tol=tolerances.ci_level,
        )
        and math.isclose(
            oracle.ci_lower / 100.0,
            expected_ci_lower,
            rel_tol=0.0,
            abs_tol=tolerances.confidence_interval,
        )
        and math.isclose(
            oracle.ci_upper / 100.0,
            expected_ci_upper,
            rel_tol=0.0,
            abs_tol=tolerances.confidence_interval,
        )
        and math.isclose(
            oracle.p_value,
            expected_p_value,
            rel_tol=0.0,
            abs_tol=tolerances.p_value,
        )
        and math.isclose(
            oracle.test_statistic,
            expected_test_statistic,
            rel_tol=0.0,
            abs_tol=tolerances.test_statistic,
        )
        and math.isclose(
            oracle.power_achieved,
            expected_power_achieved,
            rel_tol=0.0,
            abs_tol=tolerances.power_achieved,
        )
    )
    significance_contract = (
        abs(expected_p_value - request.plan.alpha) <= tolerances.p_value
        or oracle.is_significant is (expected_p_value < request.plan.alpha)
    )
    if not numeric_contract or not significance_contract:
        raise StatsKernelParityError("legacy binary oracle failed parity checks")


class LegacyStatsKernelAdapter:
    """Trialmark boundary around the unchanged AB_TEST binary results oracle."""

    def __init__(self, build: StatsKernelBuild) -> None:
        self._build = build

    @property
    def build(self) -> StatsKernelBuild:
        return self._build

    def analyze(self, request: StatsKernelRequest) -> StatsKernelResult:
        control = request.aggregates.control
        treatment = request.aggregates.treatment
        oracle = analyze_results(
            ResultsRequest(
                metric_type="binary",
                binary=ObservedResultsBinary(
                    control_conversions=control.conversions,
                    control_users=control.users,
                    treatment_conversions=treatment.conversions,
                    treatment_users=treatment.users,
                    alpha=request.plan.alpha,
                ),
            )
        )
        if (
            oracle.metric_type != "binary"
            or oracle.control_rate is None
            or oracle.treatment_rate is None
        ):
            raise StatsKernelParityError("legacy binary oracle returned an incompatible result")
        _assert_oracle_parity(oracle, request)

        estimate = StatsKernelEstimate(
            point_estimate=oracle.observed_effect / 100.0,
            control_rate=oracle.control_rate / 100.0,
            treatment_rate=oracle.treatment_rate / 100.0,
            uncertainty=StatsKernelUncertainty(
                level=oracle.ci_level,
                lower=oracle.ci_lower / 100.0,
                upper=oracle.ci_upper / 100.0,
                p_value=oracle.p_value,
            ),
            sample_size=StatsKernelSampleSize(
                total=control.users + treatment.users,
                groups=(
                    StatsKernelGroupSampleSize(
                        intervention_id=control.intervention_id,
                        users=control.users,
                    ),
                    StatsKernelGroupSampleSize(
                        intervention_id=treatment.intervention_id,
                        users=treatment.users,
                    ),
                ),
            ),
        )
        diagnostics = StatsKernelDiagnostics(
            test_statistic=oracle.test_statistic,
            is_significant=oracle.is_significant,
            power_achieved=oracle.power_achieved,
        )
        lineage = StatsKernelLineage(
            kernel_version=self._build.kernel_version,
            git_commit=self._build.git_commit,
            build_digest=self._build.build_digest,
            dependency_lock_digest=self._build.dependency_lock_digest,
            analyzer_version=request.plan.analyzer_version,
            policy_version=request.plan.policy_version,
            numeric_tolerances=request.plan.numeric_tolerances,
            random_seed=request.plan.random_seed,
            input_lineage=request.lineage,
            analysis_plan_digest=_digest(request.plan.model_dump(mode="json")),
            input_aggregate_digests=(
                _aggregate_digest("control", control),
                _aggregate_digest("treatment", treatment),
            ),
            output_estimate_digest=_digest(estimate.model_dump(mode="json")),
            output_diagnostics_digest=_digest(diagnostics.model_dump(mode="json")),
        )
        return StatsKernelResult(
            estimate=estimate,
            diagnostics=diagnostics,
            lineage=lineage,
        )
