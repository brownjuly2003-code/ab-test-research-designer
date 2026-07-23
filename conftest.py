from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    """Use a per-process basetemp instead of shared pytest temp links."""
    if getattr(config.option, "basetemp", None):
        return
    root = Path(str(config.rootpath))
    basetemp_parent = root / ".tmp"
    basetemp_parent.mkdir(parents=True, exist_ok=True)
    config.option.basetemp = str(basetemp_parent / f"pytest-basetemp-{os.getpid()}-{uuid.uuid4().hex}")
