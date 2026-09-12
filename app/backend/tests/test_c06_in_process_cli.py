"""In-process C-06 CLI shim must match the subprocess returncode contract."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.backend.app.config import get_settings
from app.backend.tests.test_c06_demo import _in_process_run_cli
from examples.demo.run_demo import DemoError, _run_cli


def _returncode_from_demo_error(error: DemoError) -> int:
    message = str(error)
    head = "Trialmark CLI returned "
    assert message.startswith(head), message
    code_text, rest = message[len(head) :].split(",", 1)
    assert rest.lstrip().startswith("expected "), message
    return int(code_text)


def test_in_process_run_cli_turns_argparse_system_exit_into_demo_error() -> None:
    with pytest.raises(DemoError, match=r"Trialmark CLI returned 2, expected 0:") as raised:
        _in_process_run_cli(
            ["not-a-command"],
            environment=os.environ.copy(),
        )

    message = str(raised.value)
    assert "invalid choice" in message
    assert "not-a-command" in message


def test_in_process_run_cli_maps_non_integer_system_exit_to_returncode_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_non_integer_exit(_arguments: list[str]) -> int:
        raise SystemExit("stats kernel Git provenance is unavailable")

    monkeypatch.setattr(
        "app.backend.tests.test_c06_demo.trialmark_cli_main",
        _raise_non_integer_exit,
    )

    with pytest.raises(DemoError, match=r"Trialmark CLI returned 1, expected 0:") as raised:
        _in_process_run_cli(
            ["runs", "list"],
            environment=os.environ.copy(),
        )

    assert "stats kernel Git provenance is unavailable" in str(raised.value)


def test_in_process_run_cli_maps_none_system_exit_to_returncode_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_none_exit(_arguments: list[str]) -> int:
        raise SystemExit(None)

    monkeypatch.setattr(
        "app.backend.tests.test_c06_demo.trialmark_cli_main",
        _raise_none_exit,
    )

    with pytest.raises(DemoError) as raised:
        _in_process_run_cli(
            ["runs", "list"],
            environment=os.environ.copy(),
            expected_returncode=99,
        )

    assert _returncode_from_demo_error(raised.value) == 0


def test_in_process_run_cli_matches_subprocess_argparse_demo_error_shape() -> None:
    environment = os.environ.copy()
    with pytest.raises(DemoError, match=r"Trialmark CLI returned 2, expected 0:") as shim_raised:
        _in_process_run_cli(["not-a-command"], environment=environment)
    with pytest.raises(DemoError, match=r"Trialmark CLI returned 2, expected 0:") as real_raised:
        _run_cli(["not-a-command"], environment=environment)

    shim_message = str(shim_raised.value)
    real_message = str(real_raised.value)
    assert "invalid choice" in shim_message
    assert "invalid choice" in real_message
    assert "not-a-command" in shim_message
    assert "not-a-command" in real_message


@pytest.mark.parametrize(
    ("snippet", "exit_code"),
    [
        ("import sys; sys.exit()", None),
        ("import sys; sys.exit(0)", 0),
        ("import sys; sys.exit(2)", 2),
        ("import sys; sys.exit('boom')", "boom"),
    ],
)
def test_in_process_run_cli_returncode_matches_real_process_exit(
    monkeypatch: pytest.MonkeyPatch,
    snippet: str,
    exit_code: int | str | None,
) -> None:
    completed = subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True,
        text=True,
        check=False,
    )

    def _raise_exit(_arguments: list[str]) -> int:
        raise SystemExit(exit_code)

    monkeypatch.setattr(
        "app.backend.tests.test_c06_demo.trialmark_cli_main",
        _raise_exit,
    )

    with pytest.raises(DemoError) as raised:
        _in_process_run_cli(
            ["runs", "list"],
            environment=os.environ.copy(),
            expected_returncode=99,
        )

    assert _returncode_from_demo_error(raised.value) == completed.returncode


def test_in_process_run_cli_turns_plain_exception_into_demo_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_value_error(_arguments: list[str]) -> int:
        raise ValueError("corrupt archive cannot be verified")

    monkeypatch.setattr(
        "app.backend.tests.test_c06_demo.trialmark_cli_main",
        _raise_value_error,
    )

    with pytest.raises(DemoError, match=r"Trialmark CLI returned 1, expected 0:") as raised:
        _in_process_run_cli(
            ["verify", "missing.tmk"],
            environment=os.environ.copy(),
        )

    message = str(raised.value)
    assert "Traceback (most recent call last)" in message
    assert "ValueError: corrupt archive cannot be verified" in message


def test_in_process_run_cli_keeps_process_env_when_caller_passes_os_environ(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = os.environ.copy()
    assert before, "process environment must start non-empty"
    seen_during: dict[str, str] = {}

    def _emit_empty_json(_arguments: list[str]) -> int:
        seen_during.update(os.environ)
        print("{}")
        return 0

    monkeypatch.setattr(
        "app.backend.tests.test_c06_demo.trialmark_cli_main",
        _emit_empty_json,
    )

    result = _in_process_run_cli(["runs", "list"], environment=os.environ)

    assert result == {}
    assert seen_during == before
    assert os.environ.copy() == before


def test_in_process_run_cli_restores_env_and_settings_if_chdir_back_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AB_APP_NAME", "t22-outer-settings")
    get_settings.cache_clear()
    assert get_settings().app_name == "t22-outer-settings"

    inner_environment = os.environ.copy()
    inner_environment["AB_APP_NAME"] = "t22-inner-settings"

    real_chdir = os.chdir
    restore_chdir = False

    def _chdir(path: str | Path) -> None:
        if restore_chdir:
            raise OSError("saved cwd is gone")
        real_chdir(path)

    def _emit_empty_json(_arguments: list[str]) -> int:
        nonlocal restore_chdir
        restore_chdir = True
        assert get_settings().app_name == "t22-inner-settings"
        print("{}")
        return 0

    monkeypatch.setattr(os, "chdir", _chdir)
    monkeypatch.setattr(
        "app.backend.tests.test_c06_demo.trialmark_cli_main",
        _emit_empty_json,
    )

    original_cwd = Path.cwd()
    try:
        result = _in_process_run_cli(
            ["runs", "list"],
            environment=inner_environment,
        )
        assert result == {}
        assert os.environ["AB_APP_NAME"] == "t22-outer-settings"
        assert get_settings().app_name == "t22-outer-settings"
    finally:
        real_chdir(original_cwd)
        get_settings.cache_clear()

