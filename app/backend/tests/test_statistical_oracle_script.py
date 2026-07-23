import subprocess
import sys


def test_statistical_oracle_self_test() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_statistical_oracle.py", "--self-test"],
        cwd=".",
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "self-test OK" in result.stdout
