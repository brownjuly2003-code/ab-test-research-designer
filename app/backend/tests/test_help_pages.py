"""The committed help*.html theory pages stay in lockstep with their generator.

The seven static pages under ``app/frontend/public/`` are build artifacts of
``scripts/build_help_pages.py`` (one template + per-language string tables).
These tests hold the invariants the generator promises: the committed pages are
exactly what the template + strings produce, every language declares its own
``lang``/``dir``, no substitution token leaks into shipped HTML, and all seven
languages share one DOM skeleton (translations may only change text, never
structure).
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[3]
OUTPUT_DIR = ROOT_DIR / "app" / "frontend" / "public"

_spec = importlib.util.spec_from_file_location(
    "build_help_pages", ROOT_DIR / "scripts" / "build_help_pages.py"
)
assert _spec is not None and _spec.loader is not None
build_help_pages = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_help_pages)


@pytest.fixture(scope="module")
def outputs() -> dict[str, str]:
    return build_help_pages.build()


def test_declares_all_seven_languages(outputs: dict[str, str]) -> None:
    assert len(build_help_pages.LANGUAGES) == 7
    assert set(outputs) == {lang["file"] for lang in build_help_pages.LANGUAGES}
    assert "help.html" in outputs  # English is the x-default page


def test_committed_pages_match_the_generator(outputs: dict[str, str]) -> None:
    """Equivalent of ``build_help_pages.py --check``: no hand-edited drift."""
    stale = []
    for filename, content in outputs.items():
        target = OUTPUT_DIR / filename
        assert target.exists(), f"{filename} is missing from app/frontend/public/"
        if target.read_text(encoding="utf-8") != content:
            stale.append(filename)
    assert not stale, (
        f"stale pages {stale}: run `python scripts/build_help_pages.py` and commit the result"
    )


def test_each_page_declares_its_language_and_direction(outputs: dict[str, str]) -> None:
    for lang in build_help_pages.LANGUAGES:
        content = outputs[lang["file"]]
        expected = f'<html lang="{lang["code"]}" dir="{lang["dir"]}">'
        assert expected in content, f"{lang['file']}: expected {expected!r}"
    assert '<html lang="ar" dir="rtl">' in outputs["help.ar.html"]


def test_no_template_tokens_leak_into_shipped_html(outputs: dict[str, str]) -> None:
    for filename, content in outputs.items():
        assert "{{" not in content, f"{filename} contains an unresolved template token"


def test_all_languages_share_one_dom_skeleton(outputs: dict[str, str]) -> None:
    """Translations may only change text: element counts must match across languages."""
    skeleton_tags = ("section", "h2", "h3", "math", "svg", "table", "figure")
    skeletons = {
        filename: {tag: len(re.findall(rf"<{tag}[\s>]", content)) for tag in skeleton_tags}
        for filename, content in outputs.items()
    }
    reference = skeletons["help.html"]
    assert all(reference[tag] > 0 for tag in ("section", "h2", "h3", "math")), reference
    for filename, counts in skeletons.items():
        assert counts == reference, f"{filename} diverges from help.html: {counts} != {reference}"
