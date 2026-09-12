from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

import pytest

_KEEP_PYTEST_BASETEMPS = 3


def _rotate_pytest_basetemps(parent: Path, keep: int = _KEEP_PYTEST_BASETEMPS) -> None:
    """Drop old pytest-basetemp-* dirs so at most *keep* newest remain."""
    candidates: list[tuple[float, Path]] = []
    for path in parent.glob("pytest-basetemp-*"):
        try:
            if path.is_dir():
                candidates.append((path.stat().st_mtime, path))
        except OSError:
            continue
    candidates.sort(reverse=True)
    for _, stale in candidates[keep:]:
        shutil.rmtree(stale, ignore_errors=True)


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    """Use a per-process basetemp instead of shared pytest temp links."""
    if getattr(config.option, "basetemp", None):
        return
    root = Path(str(config.rootpath))
    basetemp_parent = root / ".tmp"
    basetemp_parent.mkdir(parents=True, exist_ok=True)
    _rotate_pytest_basetemps(basetemp_parent)
    config.option.basetemp = str(
        basetemp_parent / f"pytest-basetemp-{os.getpid()}-{uuid.uuid4().hex}"
    )
