from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.backend.app.evidence import stats_kernel as stats_kernel_module
from app.backend.app.evidence.abx import canonical_json_bytes
from app.backend.app.evidence.stats_kernel import (
    STATS_KERNEL_BUILD_INFO_PATH,
    STATS_KERNEL_SOURCE_PATHS,
    StatsKernelBuildError,
    load_stats_kernel_build,
    write_stats_kernel_build_info,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def clear_stats_kernel_build_cache() -> Iterator[None]:
    load_stats_kernel_build.cache_clear()
    yield
    load_stats_kernel_build.cache_clear()


def _run_git(directory: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(directory), *arguments],
        capture_output=True,
        check=True,
        encoding="utf-8",
        text=True,
    )
    return completed.stdout.strip()


def _copy_kernel_sources(repository_root: Path) -> Path:
    backend_root = repository_root / "app" / "backend"
    for relative_path in (*STATS_KERNEL_SOURCE_PATHS, "requirements.txt"):
        target = backend_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((BACKEND_ROOT / relative_path).read_bytes())
    return backend_root


def _create_git_backend(repository_root: Path) -> Path:
    backend_root = _copy_kernel_sources(repository_root)
    _run_git(repository_root, "init", "--quiet")
    _run_git(repository_root, "config", "user.email", "stats-kernel@example.invalid")
    _run_git(repository_root, "config", "user.name", "Stats Kernel Test")
    _run_git(repository_root, "add", "--", "app/backend")
    _run_git(repository_root, "commit", "--quiet", "-m", "fixture")
    return backend_root


def test_build_info_tree_without_git_matches_git_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    git_backend = _create_git_backend(tmp_path / "git-tree")
    git_build = load_stats_kernel_build(backend_root=git_backend)

    runtime_root = tmp_path / "runtime-tree"
    runtime_backend = _copy_kernel_sources(runtime_root)
    stamped = write_stats_kernel_build_info(
        backend_root=runtime_backend,
        git_commit=git_build.git_commit,
    )
    payload = json.loads(stamped.read_text(encoding="utf-8"))

    def unexpected_git(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("runtime BUILD_INFO lookup must not invoke git")

    monkeypatch.setattr(stats_kernel_module, "_run_git", unexpected_git)

    assert not (runtime_root / ".git").exists()
    assert stamped == runtime_backend / STATS_KERNEL_BUILD_INFO_PATH
    assert payload == {
        "dirty": False,
        "git_commit": git_build.git_commit,
        "tracked_digest": git_build.build_digest,
    }

    runtime_build = load_stats_kernel_build(backend_root=runtime_backend)
    assert runtime_build == git_build


# Dirty/mismatched-digest/extra-key stamps: test_evidence_stats_kernel.py::test_build_identity_fails_closed_on_invalid_build_info.
@pytest.mark.parametrize(
    "git_commit",
    (
        "ABCDEF0123456789ABCDEF0123456789ABCDEF01",
        "0123456789abcdef0123456789abcdef0123456",
    ),
)
def test_invalid_git_commit_stamp_does_not_fall_back_to_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    git_commit: str,
) -> None:
    runtime_root = tmp_path / "runtime-tree"
    backend_root = _copy_kernel_sources(runtime_root)
    stamped = write_stats_kernel_build_info(
        backend_root=backend_root,
        git_commit="0123456789abcdef0123456789abcdef01234567",
    )
    payload = json.loads(stamped.read_text(encoding="utf-8"))
    payload["git_commit"] = git_commit
    stamped.write_bytes(canonical_json_bytes(payload))

    def unexpected_git(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("invalid BUILD_INFO must not fall back to git")

    monkeypatch.setattr(stats_kernel_module, "_run_git", unexpected_git)

    assert not (runtime_root / ".git").exists()
    with pytest.raises(StatsKernelBuildError) as excinfo:
        load_stats_kernel_build(backend_root=backend_root)
    assert str(excinfo.value) == "stats kernel build information is invalid"


def test_missing_build_info_and_git_raises_typed_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime-tree"
    backend_root = _copy_kernel_sources(runtime_root)
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "missing.git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "missing-work-tree"))

    assert not (runtime_root / ".git").exists()
    assert not (backend_root / STATS_KERNEL_BUILD_INFO_PATH).exists()
    with pytest.raises(StatsKernelBuildError) as error:
        load_stats_kernel_build(backend_root=backend_root)

    message = str(error.value)
    assert message == (
        "stats kernel build identity is unavailable: "
        "BUILD_INFO.json is missing and Git fallback failed"
    )
    assert message.count("unavailable") == 1
    assert isinstance(error.value.__cause__, StatsKernelBuildError)
    assert str(tmp_path) not in message


def test_dirty_git_fallback_does_not_blame_missing_build_info(tmp_path: Path) -> None:
    git_backend = _create_git_backend(tmp_path / "git-tree")
    source = git_backend / STATS_KERNEL_SOURCE_PATHS[0]
    source.write_bytes(source.read_bytes() + b"\n")
    assert not (git_backend / STATS_KERNEL_BUILD_INFO_PATH).exists()

    with pytest.raises(StatsKernelBuildError) as error:
        load_stats_kernel_build(backend_root=git_backend)

    message = str(error.value)
    assert "BUILD_INFO.json is missing" not in message
    assert str(tmp_path) not in message


def test_untracked_kernel_path_does_not_blame_missing_build_info(tmp_path: Path) -> None:
    repository_root = tmp_path / "git-tree"
    git_backend = _create_git_backend(repository_root)
    relative = (Path("app") / "backend" / STATS_KERNEL_SOURCE_PATHS[0]).as_posix()
    _run_git(repository_root, "rm", "--cached", "--quiet", "--", relative)
    assert not (git_backend / STATS_KERNEL_BUILD_INFO_PATH).exists()

    with pytest.raises(StatsKernelBuildError) as error:
        load_stats_kernel_build(backend_root=git_backend)

    message = str(error.value)
    assert "BUILD_INFO.json is missing" not in message
    assert str(tmp_path) not in message


def test_lru_cache_starts_empty_and_returns_identical_object(
    tmp_path: Path,
) -> None:
    assert load_stats_kernel_build.cache_info().currsize == 0
    git_backend = _create_git_backend(tmp_path / "git-tree")
    first = load_stats_kernel_build(backend_root=git_backend)
    second = load_stats_kernel_build(backend_root=git_backend)
    assert load_stats_kernel_build.cache_info().currsize == 1
    assert second is first


def test_dockerfile_stamps_build_info_from_ab_build_sha() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "ENV AB_BUILD_SHA=${GIT_SHA}" in dockerfile
    assert "write_stats_kernel_build_info" in dockerfile
    assert "os.environ['AB_BUILD_SHA']" in dockerfile
    stamp = dockerfile.index("write_stats_kernel_build_info")
    assert dockerfile.index("ENV AB_BUILD_SHA=${GIT_SHA}") < stamp
    assert stamp < dockerfile.index("USER app")
