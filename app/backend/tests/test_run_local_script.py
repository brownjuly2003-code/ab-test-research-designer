"""Cross-platform no-Docker bootstrap/runner contract."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts import run_local


def test_local_environment_pins_sqlite_and_scrubs_hosted_secrets(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "projects.sqlite3"
    environment = run_local.build_environment(
        host="127.0.0.1",
        port=8008,
        db_path=db_path,
        seed_demo=False,
        base_environment={
            "KEEP_ME": "yes",
            "AB_ENV": "production",
            "AB_DATABASE_URL": "postgresql://remote/ab",
            "AB_HF_TOKEN": "parent-hf-token",
            "AB_HF_SNAPSHOT_REPO": "owner/private",
            "AB_API_TOKEN": "parent-api-token",
            "AB_ADMIN_TOKEN": "parent-admin-token",
            "AB_PUBLIC_DEMO": "true",
        },
    )

    assert environment["KEEP_ME"] == "yes"
    assert environment["AB_ENV"] == "local"
    assert environment["AB_DB_PATH"] == str(db_path.resolve())
    assert environment["AB_HOST"] == "127.0.0.1"
    assert environment["AB_PORT"] == "8008"
    assert environment["AB_SERVE_FRONTEND_DIST"] == "true"
    assert environment["AB_FRONTEND_DIST_PATH"] == str(run_local.FRONTEND_DIST_DIR)
    assert environment["AB_PUBLIC_DEMO"] == "false"
    assert environment["AB_SEED_DEMO_ON_STARTUP"] == "false"
    assert "AB_DATABASE_URL" not in environment
    assert "AB_HF_TOKEN" not in environment
    assert "AB_HF_SNAPSHOT_REPO" not in environment
    assert "AB_API_TOKEN" not in environment
    assert "AB_ADMIN_TOKEN" not in environment


def test_bootstrap_uses_venv_and_locked_frontend_install(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    venv_dir = tmp_path / ".venv"
    venv_python = venv_dir / (
        "Scripts/python.exe" if run_local.os.name == "nt" else "bin/python"
    )
    frontend_dir = tmp_path / "frontend"
    requirements = tmp_path / "requirements.txt"
    commands: list[tuple[list[str], Path]] = []

    monkeypatch.setattr(run_local, "VENV_DIR", venv_dir)
    monkeypatch.setattr(run_local, "VENV_PYTHON", venv_python)
    monkeypatch.setattr(run_local, "FRONTEND_DIR", frontend_dir)
    monkeypatch.setattr(run_local, "BACKEND_REQUIREMENTS", requirements)
    monkeypatch.setattr(run_local.shutil, "which", lambda executable: executable)
    monkeypatch.setattr(
        run_local,
        "run_command",
        lambda command, cwd: commands.append((command, cwd)),
    )

    run_local.bootstrap_local()

    assert commands == [
        ([sys.executable, "-m", "venv", str(venv_dir)], run_local.ROOT_DIR),
        (
            [
                str(venv_python),
                "-m",
                "pip",
                "install",
                "-r",
                str(requirements),
            ],
            run_local.ROOT_DIR,
        ),
        ([run_local.NPM_EXECUTABLE, "ci"], frontend_dir),
        ([run_local.NPM_EXECUTABLE, "run", "build"], frontend_dir),
    ]


def test_prepared_runtime_requires_venv_and_frontend_dist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(run_local, "VENV_PYTHON", tmp_path / "missing-python")
    monkeypatch.setattr(run_local, "FRONTEND_INDEX", tmp_path / "missing-index.html")

    with pytest.raises(RuntimeError, match="--bootstrap"):
        run_local.require_prepared_runtime()


def test_python_313_is_the_local_compatibility_floor() -> None:
    with pytest.raises(RuntimeError, match="3.13"):
        run_local.require_supported_python((3, 12, 9))

    run_local.require_supported_python((3, 13, 0))
