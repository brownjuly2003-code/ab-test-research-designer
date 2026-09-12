from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_runtime_image_installs_trialmark_console_entrypoint() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

    copy_metadata = "COPY pyproject.toml /app/pyproject.toml"
    install_project = "RUN pip install --no-cache-dir --no-deps ."
    assert copy_metadata in dockerfile
    assert install_project in dockerfile
    assert dockerfile.index(copy_metadata) < dockerfile.index(install_project)
    assert dockerfile.index("COPY app /app/app") < dockerfile.index(install_project)
    assert dockerfile.index(install_project) < dockerfile.index("USER app")
    assert "ENV PYTHONPATH=/app" in dockerfile
    assert dockerfile.rindex("WORKDIR /app/data") > dockerfile.index("USER app")


def test_compose_requires_build_sha_and_forwards_startup_seed() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "GIT_SHA: ${GIT_SHA:?GIT_SHA must be the exact source commit}" in compose
    assert (
        "AB_SEED_DEMO_ON_STARTUP: ${AB_SEED_DEMO_ON_STARTUP:-false}" in compose
    )


def test_container_verifier_exercises_b08_runtime_contract() -> None:
    verifier = (REPO_ROOT / "scripts" / "verify_docker_compose.py").read_text(
        encoding="utf-8"
    )

    assert 'env["GIT_SHA"] = resolve_source_commit()' in verifier
    assert 'env["AB_SEED_DEMO_ON_STARTUP"] = "true"' in verifier
    assert 'SERVICE_NAME, "trialmark", "--help"' in verifier
    assert "/app/app/backend/BUILD_INFO.json" in verifier
    assert 'http_request("GET", "/api/v2/runs"' in verifier
    assert "asos-public-benchmark-d53f0e" in verifier
