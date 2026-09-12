from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.backend.app.evidence import stats_kernel as stats_kernel_module
from app.backend.app.evidence.abx import canonical_json_bytes
from app.backend.app.evidence.stats_kernel import (
    ABX_SCHEMA_SOURCE_PATHS,
    BINARY_ANALYZER_VERSION,
    BINARY_POLICY_VERSION,
    STATS_KERNEL_ADAPTER_VERSION,
    STATS_KERNEL_SOURCE_PATHS,
    STATS_KERNEL_VERSION,
    AnalysisPlan,
    BinaryArmStatistics,
    BinarySufficientStatistics,
    LegacyStatsKernelAdapter,
    StatsKernelBuild,
    StatsKernelBuildError,
    StatsKernelInputLineage,
    StatsKernelNumericTolerances,
    StatsKernelParityError,
    StatsKernelRequest,
    load_stats_kernel_build,
)
from app.backend.app.i18n import reset_current_language, set_current_language
from app.backend.app.schemas.api import ObservedResultsBinary, ResultsRequest
from app.backend.app.services.results_service import analyze_results

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _run_git(directory: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(directory), *arguments],
        capture_output=True,
        check=True,
        encoding="utf-8",
        text=True,
    )
    return completed.stdout.strip()


def _create_build_repository(repository_root: Path) -> Path:
    backend_root = repository_root / "app" / "backend"
    for relative_path in (*STATS_KERNEL_SOURCE_PATHS, "requirements.txt"):
        target = backend_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((BACKEND_ROOT / relative_path).read_bytes())
    _run_git(repository_root, "init", "--quiet")
    _run_git(repository_root, "config", "user.email", "stats-kernel@example.invalid")
    _run_git(repository_root, "config", "user.name", "Stats Kernel Test")
    _run_git(repository_root, "add", "--", "app/backend")
    _run_git(repository_root, "commit", "--quiet", "-m", "fixture")
    return backend_root


def _create_runtime_build_tree(runtime_root: Path, *, git_commit: str) -> Path:
    backend_root = runtime_root / "app" / "backend"
    source_records = []
    for relative_path in (*STATS_KERNEL_SOURCE_PATHS, "requirements.txt"):
        target = backend_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((BACKEND_ROOT / relative_path).read_bytes())
        if relative_path in STATS_KERNEL_SOURCE_PATHS:
            source_records.append(
                {"path": relative_path, "digest": _file_digest(target)}
            )
    (backend_root / "BUILD_INFO.json").write_bytes(
        canonical_json_bytes(
            {
                "git_commit": git_commit,
                "dirty": False,
                "tracked_digest": _digest({"sources": source_records}),
            }
        )
    )
    return backend_root


@pytest.fixture(scope="module")
def verified_build_environment(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[StatsKernelBuild, Path]:
    backend_root = _create_build_repository(
        tmp_path_factory.mktemp("stats-kernel-build")
    )
    return load_stats_kernel_build(backend_root=backend_root), backend_root


def _request(*, treatment_conversions: int = 130) -> StatsKernelRequest:
    return StatsKernelRequest(
        plan=AnalysisPlan(alpha=0.05),
        aggregates=BinarySufficientStatistics(
            control=BinaryArmStatistics(
                intervention_id="control",
                conversions=100,
                users=1000,
            ),
            treatment=BinaryArmStatistics(
                intervention_id="treatment",
                conversions=treatment_conversions,
                users=1000,
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


def _oracle(request: StatsKernelRequest):  # type: ignore[no-untyped-def]
    return analyze_results(
        ResultsRequest(
            metric_type="binary",
            binary=ObservedResultsBinary(
                control_conversions=request.aggregates.control.conversions,
                control_users=request.aggregates.control.users,
                treatment_conversions=request.aggregates.treatment.conversions,
                treatment_users=request.aggregates.treatment.users,
                alpha=request.plan.alpha,
            ),
        )
    )


def test_binary_adapter_preserves_legacy_oracle_and_records_lineage(
    verified_build_environment: tuple[StatsKernelBuild, Path],
) -> None:
    build, _backend_root = verified_build_environment
    request = _request()

    result = LegacyStatsKernelAdapter(build).analyze(request)
    oracle = _oracle(request)

    assert result.estimate.effect_measure == "risk_difference"
    assert result.estimate.point_estimate == oracle.observed_effect / 100.0
    assert result.estimate.control_rate == oracle.control_rate / 100.0  # type: ignore[operator]
    assert result.estimate.treatment_rate == oracle.treatment_rate / 100.0  # type: ignore[operator]
    assert result.estimate.uncertainty.lower == oracle.ci_lower / 100.0
    assert result.estimate.uncertainty.upper == oracle.ci_upper / 100.0
    assert result.estimate.uncertainty.level == oracle.ci_level
    assert result.estimate.uncertainty.p_value == oracle.p_value
    assert result.estimate.sample_size.total == 2000
    assert tuple(
        (group.intervention_id, group.users)
        for group in result.estimate.sample_size.groups
    ) == (("control", 1000), ("treatment", 1000))
    assert result.diagnostics.test_statistic == oracle.test_statistic
    assert result.diagnostics.is_significant is oracle.is_significant
    assert result.diagnostics.power_achieved == oracle.power_achieved

    # Independent frozen oracle case: 130/1000 versus 100/1000, Newcombe 95% CI.
    assert result.estimate.point_estimate == 0.03
    assert result.estimate.control_rate == 0.1
    assert result.estimate.treatment_rate == 0.13
    assert result.estimate.uncertainty.lower == 0.002002
    assert result.estimate.uncertainty.upper == pytest.approx(0.05807, abs=1e-12)
    assert result.estimate.uncertainty.p_value == 0.035488
    assert result.diagnostics.test_statistic == 2.1027
    assert result.diagnostics.is_significant is True
    assert result.diagnostics.power_achieved == 0.557

    lineage = result.lineage
    assert lineage.kernel_name == "legacy_stats_kernel"
    assert lineage.kernel_version == STATS_KERNEL_VERSION == build.kernel_version
    assert lineage.adapter_version == STATS_KERNEL_ADAPTER_VERSION
    assert lineage.git_commit == build.git_commit
    assert lineage.build_digest == build.build_digest
    assert lineage.dependency_lock_digest == build.dependency_lock_digest
    assert lineage.analyzer_version == BINARY_ANALYZER_VERSION
    assert lineage.policy_version == BINARY_POLICY_VERSION
    assert lineage.numeric_tolerances == request.plan.numeric_tolerances
    assert lineage.random_seed is None
    assert lineage.input_lineage == request.lineage
    assert lineage.analysis_plan_digest == _digest(request.plan.model_dump(mode="json"))
    assert lineage.input_aggregate_digests == (
        _digest(
            {
                "conversions": 100,
                "intervention_id": "control",
                "role": "control",
                "users": 1000,
            }
        ),
        _digest(
            {
                "conversions": 130,
                "intervention_id": "treatment",
                "role": "treatment",
                "users": 1000,
            }
        ),
    )
    assert lineage.output_estimate_digest == _digest(
        result.estimate.model_dump(mode="json")
    )
    assert lineage.output_diagnostics_digest == _digest(
        result.diagnostics.model_dump(mode="json")
    )


def test_build_identity_hashes_required_sources_lock_and_verified_commit(
    verified_build_environment: tuple[StatsKernelBuild, Path],
) -> None:
    build, backend_root = verified_build_environment
    source_records = [
        {"path": relative_path, "digest": _file_digest(backend_root / relative_path)}
        for relative_path in STATS_KERNEL_SOURCE_PATHS
    ]

    schema_root = BACKEND_ROOT / "app/evidence/contracts/schemas/abx/0.1"
    actual_schema_paths = tuple(
        path.relative_to(BACKEND_ROOT).as_posix()
        for path in sorted(schema_root.glob("*.schema.json"))
    )

    abx_root = BACKEND_ROOT / "app/evidence/abx"
    actual_abx_paths = tuple(
        path.relative_to(BACKEND_ROOT).as_posix()
        for path in sorted(abx_root.glob("*.py"))
    )

    # Derived from the directory, not spelled out again: a new abx module
    # that nobody adds to STATS_KERNEL_SOURCE_PATHS would otherwise change
    # the kernel without changing its digest.
    assert actual_abx_paths
    assert set(actual_abx_paths) <= set(STATS_KERNEL_SOURCE_PATHS)
    assert ABX_SCHEMA_SOURCE_PATHS == actual_schema_paths
    assert set(ABX_SCHEMA_SOURCE_PATHS) <= set(STATS_KERNEL_SOURCE_PATHS)
    assert build.git_commit == _run_git(backend_root, "rev-parse", "HEAD")
    assert build.build_digest == _digest({"sources": source_records})
    assert build.dependency_lock_digest == _file_digest(backend_root / "requirements.txt")


def test_build_identity_uses_cached_build_info_without_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    git_commit = "0123456789abcdef0123456789abcdef01234567"
    backend_root = _create_runtime_build_tree(
        tmp_path / "runtime",
        git_commit=git_commit,
    )

    def unexpected_git(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("runtime BUILD_INFO lookup must not invoke git")

    monkeypatch.setattr(stats_kernel_module, "_run_git", unexpected_git)

    first = load_stats_kernel_build(backend_root=backend_root)
    (backend_root / STATS_KERNEL_SOURCE_PATHS[0]).write_bytes(b"changed after load")
    second = load_stats_kernel_build(backend_root=backend_root)

    assert first.git_commit == git_commit
    assert first.build_digest == _digest(
        {
            "sources": [
                {
                    "path": relative_path,
                    "digest": _file_digest(BACKEND_ROOT / relative_path),
                }
                for relative_path in STATS_KERNEL_SOURCE_PATHS
            ]
        }
    )
    assert first.dependency_lock_digest == _file_digest(
        backend_root / "requirements.txt"
    )
    assert second is first


@pytest.mark.parametrize(
    "build_info_update",
    (
        {"dirty": True},
        {"tracked_digest": "sha256:" + "f" * 64},
        {"unexpected": "value"},
    ),
)
def test_build_identity_fails_closed_on_invalid_build_info(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    build_info_update: dict[str, object],
) -> None:
    backend_root = _create_runtime_build_tree(
        tmp_path / "runtime",
        git_commit="0123456789abcdef0123456789abcdef01234567",
    )
    source_records = [
        {
            "path": relative_path,
            "digest": _file_digest(backend_root / relative_path),
        }
        for relative_path in STATS_KERNEL_SOURCE_PATHS
    ]
    build_info: dict[str, object] = {
        "git_commit": "0123456789abcdef0123456789abcdef01234567",
        "dirty": False,
        "tracked_digest": _digest({"sources": source_records}),
    }
    build_info.update(build_info_update)
    (backend_root / "BUILD_INFO.json").write_bytes(
        canonical_json_bytes(build_info)
    )

    def unexpected_git(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("invalid BUILD_INFO must not fall back to git")

    monkeypatch.setattr(stats_kernel_module, "_run_git", unexpected_git)

    with pytest.raises(StatsKernelBuildError):
        load_stats_kernel_build(backend_root=backend_root)


def test_build_identity_fails_closed_on_dirty_source_or_missing_lock(
    tmp_path: Path,
) -> None:
    git_commit = "0123456789abcdef0123456789abcdef01234567"
    dirty_backend = _create_runtime_build_tree(tmp_path / "dirty", git_commit=git_commit)
    dirty_source = dirty_backend / STATS_KERNEL_SOURCE_PATHS[0]
    dirty_source.write_bytes(dirty_source.read_bytes() + b"\n")
    with pytest.raises(StatsKernelBuildError) as dirty_error:
        load_stats_kernel_build(backend_root=dirty_backend)

    missing_backend = _create_runtime_build_tree(
        tmp_path / "missing",
        git_commit=git_commit,
    )
    (missing_backend / "requirements.txt").unlink()
    with pytest.raises(StatsKernelBuildError) as missing_error:
        load_stats_kernel_build(backend_root=missing_backend)

    dirty_schema_backend = _create_runtime_build_tree(
        tmp_path / "dirty-schema",
        git_commit=git_commit,
    )
    dirty_schema = dirty_schema_backend / ABX_SCHEMA_SOURCE_PATHS[0]
    dirty_schema.write_bytes(dirty_schema.read_bytes() + b"\n")
    with pytest.raises(StatsKernelBuildError) as dirty_schema_error:
        load_stats_kernel_build(backend_root=dirty_schema_backend)

    assert str(tmp_path) not in str(dirty_error.value)
    assert str(tmp_path) not in str(missing_error.value)
    assert str(tmp_path) not in str(dirty_schema_error.value)


def test_result_is_repeatable_locale_independent_and_contains_no_display_text(
    verified_build_environment: tuple[StatsKernelBuild, Path],
) -> None:
    build, _backend_root = verified_build_environment
    adapter = LegacyStatsKernelAdapter(build)
    request = _request()

    english_token = set_current_language("en")
    try:
        english = adapter.analyze(request)
    finally:
        reset_current_language(english_token)

    russian_token = set_current_language("ru")
    try:
        russian = adapter.analyze(request)
    finally:
        reset_current_language(russian_token)

    assert russian.model_dump_json() == english.model_dump_json()
    serialized = english.model_dump_json()
    assert "verdict" not in serialized
    assert "interpretation" not in serialized
    assert "postgresql://" not in serialized
    assert "SELECT " not in serialized
    assert str(BACKEND_ROOT) not in serialized


def test_changed_aggregate_changes_input_and_output_digests(
    verified_build_environment: tuple[StatsKernelBuild, Path],
) -> None:
    build, _backend_root = verified_build_environment
    adapter = LegacyStatsKernelAdapter(build)

    original = adapter.analyze(_request(treatment_conversions=130))
    changed = adapter.analyze(_request(treatment_conversions=131))

    assert changed.lineage.input_aggregate_digests[0] == (
        original.lineage.input_aggregate_digests[0]
    )
    assert changed.lineage.input_aggregate_digests[1] != (
        original.lineage.input_aggregate_digests[1]
    )
    assert changed.lineage.output_estimate_digest != original.lineage.output_estimate_digest
    assert changed.lineage.output_diagnostics_digest != (
        original.lineage.output_diagnostics_digest
    )


@pytest.mark.parametrize(
    "oracle_update",
    [
        {"control_rate": 11.0},
        {"treatment_rate": 14.0},
        {"observed_effect": 4.0},
        {"ci_level": 0.9},
        {"is_significant": False},
    ],
)
def test_adapter_stops_on_oracle_contract_drift(
    monkeypatch: pytest.MonkeyPatch,
    verified_build_environment: tuple[StatsKernelBuild, Path],
    oracle_update: dict[str, object],
) -> None:
    build, _backend_root = verified_build_environment
    request = _request()
    drifted_oracle = _oracle(request).model_copy(update=oracle_update)
    call_count = 0

    def fake_analyze_results(_request: ResultsRequest):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        return drifted_oracle

    monkeypatch.setattr(stats_kernel_module, "analyze_results", fake_analyze_results)

    with pytest.raises(StatsKernelParityError, match="failed parity checks"):
        LegacyStatsKernelAdapter(build).analyze(request)
    assert call_count == 1


@pytest.mark.parametrize(
    "oracle_update",
    [
        pytest.param({"p_value": 0.35488}, id="p-times-ten"),
        pytest.param({"p_value": 0.5}, id="p-fixed-half"),
        pytest.param(
            {"ci_lower": 20.02, "ci_upper": 580.7},
            id="ci-times-one-hundred",
        ),
        pytest.param({"ci_lower": 0.0, "ci_upper": 0.0}, id="ci-zeroed"),
        pytest.param({"power_achieved": 0.0}, id="power-zeroed"),
        pytest.param({"test_statistic": 0.0}, id="z-zeroed"),
    ],
)
def test_parity_mutation_guards_reject_independently_wrong_oracle_fields(
    monkeypatch: pytest.MonkeyPatch,
    verified_build_environment: tuple[StatsKernelBuild, Path],
    oracle_update: dict[str, object],
) -> None:
    build, _backend_root = verified_build_environment
    request = _request()
    drifted_oracle = _oracle(request).model_copy(update=oracle_update)

    monkeypatch.setattr(
        stats_kernel_module,
        "analyze_results",
        lambda _request: drifted_oracle,
    )

    with pytest.raises(StatsKernelParityError, match="failed parity checks"):
        LegacyStatsKernelAdapter(build).analyze(request)


def test_adapter_reports_degenerate_newcombe_interval(
    verified_build_environment: tuple[StatsKernelBuild, Path],
) -> None:
    build, _backend_root = verified_build_environment
    base_request = _request()
    request = StatsKernelRequest(
        plan=base_request.plan,
        lineage=base_request.lineage,
        aggregates=BinarySufficientStatistics(
            control=BinaryArmStatistics(
                intervention_id="control",
                conversions=0,
                users=50,
            ),
            treatment=BinaryArmStatistics(
                intervention_id="treatment",
                conversions=0,
                users=50,
            ),
        ),
    )

    result = LegacyStatsKernelAdapter(build).analyze(request)

    assert result.estimate.point_estimate == 0.0
    assert result.estimate.uncertainty.lower == pytest.approx(-0.071348, abs=1e-12)
    assert result.estimate.uncertainty.upper == pytest.approx(0.071348, abs=1e-12)
    assert result.estimate.uncertainty.p_value == 1.0
    assert result.diagnostics.test_statistic == 0.0
    assert result.diagnostics.is_significant is False
    assert result.diagnostics.power_achieved == 0.0


def test_contracts_fail_closed_for_invalid_plans_counts_and_build_inputs(
    verified_build_environment: tuple[StatsKernelBuild, Path],
) -> None:
    with pytest.raises(ValidationError):
        AnalysisPlan(alpha="0.05")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        AnalysisPlan(alpha=float("nan"))
    with pytest.raises(ValidationError):
        AnalysisPlan.model_validate({"alpha": 0.05, "method": "auto"})
    with pytest.raises(ValidationError):
        AnalysisPlan.model_validate({"alpha": 0.05, "unexpected": "value"})
    with pytest.raises(ValidationError):
        StatsKernelNumericTolerances(point_estimate=1e-3)
    with pytest.raises(ValidationError):
        BinaryArmStatistics(  # type: ignore[arg-type]
            intervention_id="control",
            conversions=False,
            users=2,
        )
    with pytest.raises(ValidationError, match="conversions cannot exceed users"):
        BinaryArmStatistics(
            intervention_id="control",
            conversions=3,
            users=2,
        )
    with pytest.raises(ValidationError, match="different intervention IDs"):
        BinarySufficientStatistics(
            control=BinaryArmStatistics(
                intervention_id="same",
                conversions=0,
                users=2,
            ),
            treatment=BinaryArmStatistics(
                intervention_id="same",
                conversions=0,
                users=2,
            ),
        )

    digest = "sha256:" + "f" * 64
    with pytest.raises(ValidationError):
        StatsKernelBuild(
            git_commit="unknown",
            build_digest=digest,
            dependency_lock_digest=digest,
        )

    build, _backend_root = verified_build_environment
    result = LegacyStatsKernelAdapter(build).analyze(_request())
    with pytest.raises(ValidationError, match="frozen"):
        result.estimate.point_estimate = 99.0
