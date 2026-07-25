"""README Local setup must document the downloadable local product (not HF demo)."""

from __future__ import annotations

from pathlib import Path


def _local_setup_section() -> str:
    """Extract README.md ``## Local setup`` through the next H2 (not ###)."""
    readme = Path(__file__).resolve().parents[3] / "README.md"
    lines = readme.read_text(encoding="utf-8").splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.startswith("## Local setup"))
    end = start + 1
    while end < len(lines) and not (
        lines[end].startswith("## ") and not lines[end].startswith("### ")
    ):
        end += 1
    return "".join(lines[start:end])


def test_local_setup_documents_downloadable_product_vs_hf_demo() -> None:
    section = _local_setup_section()

    assert "SQLite" in section
    assert "no secrets" in section

    assert "LLM" in section
    assert "pasted" in section.lower()
    assert "browser-session-only" in section
    assert "backend env" in section

    assert "No Docker" in section
    assert "python scripts/run_local.py --bootstrap" in section
    assert "python scripts/run_local.py --seed-demo" in section
    assert section.index("python scripts/run_local.py --bootstrap") < section.index(
        "docker compose up --build"
    )

    assert "Python 3.13+" in section
    assert "CI and mypy use Python 3.14" in section
    assert "python -m venv .venv" in section
    assert "python -m pip install -r app/backend/requirements.txt" in section
    assert "npm --prefix app/frontend ci" in section
    assert "npm --prefix app/frontend run build" in section

    assert "Docker (optional)" in section
    assert "docker compose up --build" in section
    assert "127.0.0.1:8008" in section

    assert "AB_SEED_DEMO_ON_STARTUP=true" in section
    assert "HF demo" in section or "Hugging Face" in section

    assert "### Backend" in section
    assert "### Frontend" in section
    assert "uvicorn" in section
    assert "npm run dev" in section
