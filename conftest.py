from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    """Use a per-process basetemp on Windows instead of shared pytest temp links."""
    if getattr(config.option, "basetemp", None):
        return
    root = Path(str(config.rootpath))
    config.option.basetemp = str(root / ".tmp" / f"pytest-basetemp-{os.getpid()}-{uuid.uuid4().hex}")
