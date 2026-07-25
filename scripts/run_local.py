"""Bootstrap and run the single-port local product without Docker."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT_DIR / ".venv"
VENV_PYTHON = VENV_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
FRONTEND_DIR = ROOT_DIR / "app" / "frontend"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"
FRONTEND_INDEX = FRONTEND_DIST_DIR / "index.html"
BACKEND_REQUIREMENTS = ROOT_DIR / "app" / "backend" / "requirements.txt"
DEFAULT_DB_PATH = ROOT_DIR / "app" / "backend" / "data" / "projects.sqlite3"
NPM_EXECUTABLE = "npm.cmd" if os.name == "nt" else "npm"


def require_supported_python(
    version: tuple[int, int, int] | None = None,
) -> None:
    resolved = version or sys.version_info[:3]
    if resolved < (3, 13, 0):
        raise RuntimeError(
            "Python 3.13+ is required for local use (CI and mypy target Python 3.14)."
        )


def _display_command(command: Sequence[str]) -> str:
    return subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command)


def run_command(command: list[str], cwd: Path) -> None:
    print(f"+ {_display_command(command)}")
    subprocess.run(command, cwd=cwd, check=True)


def bootstrap_local() -> None:
    """Create/update local dependencies and build the locked frontend."""
    require_supported_python()
    if shutil.which(NPM_EXECUTABLE) is None:
        raise RuntimeError(
            "Node.js/npm is required for --bootstrap but npm was not found."
        )

    if not VENV_PYTHON.exists():
        run_command([sys.executable, "-m", "venv", str(VENV_DIR)], ROOT_DIR)

    run_command(
        [
            str(VENV_PYTHON),
            "-m",
            "pip",
            "install",
            "-r",
            str(BACKEND_REQUIREMENTS),
        ],
        ROOT_DIR,
    )
    run_command([NPM_EXECUTABLE, "ci"], FRONTEND_DIR)
    run_command([NPM_EXECUTABLE, "run", "build"], FRONTEND_DIR)


def require_prepared_runtime() -> None:
    missing: list[str] = []
    if not VENV_PYTHON.is_file():
        missing.append(str(VENV_PYTHON))
    if not FRONTEND_INDEX.is_file():
        missing.append(str(FRONTEND_INDEX))
    if missing:
        formatted = "\n- ".join(missing)
        raise RuntimeError(
            "Local runtime is not prepared. Missing:\n"
            f"- {formatted}\n"
            "Run `python scripts/run_local.py --bootstrap` to install/build explicitly."
        )


def build_environment(
    *,
    host: str,
    port: int,
    db_path: Path,
    seed_demo: bool,
    base_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return an isolated SQLite/local child environment."""
    environment = dict(os.environ if base_environment is None else base_environment)
    exact_external_keys = {
        "AB_DATABASE_URL",
        "AB_HF_TOKEN",
        "AB_HF_SNAPSHOT_REPO",
        "AB_HF_SNAPSHOT_INTERVAL_SECONDS",
        "HF_TOKEN",
        "AB_API_TOKEN",
        "AB_READONLY_API_TOKEN",
        "AB_ADMIN_TOKEN",
        "AB_WORKSPACE_SIGNING_KEY",
        "AB_MISTRAL_API_KEY",
        "MISTRAL_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "AB_ALLOW_INSECURE_PRODUCTION",
    }
    for name in tuple(environment):
        if name in exact_external_keys or name.startswith("AB_SLACK_"):
            environment.pop(name, None)

    environment.update(
        {
            "AB_ENV": "local",
            "AB_HOST": host,
            "AB_PORT": str(port),
            "AB_DB_PATH": str(db_path.resolve()),
            "AB_SERVE_FRONTEND_DIST": "true",
            "AB_FRONTEND_DIST_PATH": str(FRONTEND_DIST_DIR),
            "AB_PUBLIC_DEMO": "false",
            "AB_SEED_DEMO_ON_STARTUP": "true" if seed_demo else "false",
        }
    )
    return environment


def serve_local(environment: dict[str, str], *, host: str, port: int) -> None:
    command = [
        str(VENV_PYTHON),
        "-m",
        "uvicorn",
        "app.backend.app.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    print(f"+ {_display_command(command)}")
    subprocess.run(command, cwd=ROOT_DIR, env=environment, check=True)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the AB-test designer UI and API locally without Docker."
    )
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Explicitly create/update .venv, install backend requirements, and run npm ci/build.",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Validate (or bootstrap) the local runtime, then exit without serving.",
    )
    parser.add_argument(
        "--seed-demo",
        action="store_true",
        help="Seed the four local demo projects on startup.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=_positive_int, default=8008)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    require_supported_python()
    if args.bootstrap:
        print("Bootstrap explicitly installs locked Python/npm dependencies.")
        bootstrap_local()
    require_prepared_runtime()
    if args.prepare_only:
        print("Local runtime is ready.")
        return 0

    environment = build_environment(
        host=args.host,
        port=args.port,
        db_path=args.db_path,
        seed_demo=args.seed_demo,
    )
    print(f"Starting AB-test designer at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        serve_local(environment, host=args.host, port=args.port)
    except KeyboardInterrupt:
        print("\nLocal AB-test designer stopped.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
