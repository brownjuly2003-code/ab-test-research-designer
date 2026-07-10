"""Build the static theory-reference pages (help*.html) from a single template.

One HTML template (``scripts/help_pages/template.html``) holds the entire page
structure — markup, CSS, MathML formulas, SVG figures. Everything language-visible
lives in per-language string tables (``scripts/help_pages/strings/<lang>.json``).
The build substitutes ``{{key}}`` tokens and writes one self-contained page per
language into ``app/frontend/public/``, which Vite copies into the frontend dist
and the backend serves as-is.

Why generated: seven languages sharing one DOM. Editing seven hand-written HTML
files drifts apart silently; here structure can only change in one place, and a
translation can only change text. CI runs ``--check`` so the committed pages are
always exactly what the template + strings produce.

Usage:
    python scripts/build_help_pages.py            # rebuild pages in place
    python scripts/build_help_pages.py --check    # verify committed pages match (CI)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT_DIR / "scripts" / "help_pages" / "template.html"
STRINGS_DIR = ROOT_DIR / "scripts" / "help_pages" / "strings"
OUTPUT_DIR = ROOT_DIR / "app" / "frontend" / "public"

# Order defines the language-menu order on every page.
LANGUAGES: list[dict[str, str]] = [
    {"code": "en", "file": "help.html", "dir": "ltr", "label": "EN", "name": "English"},
    {"code": "ru", "file": "help.ru.html", "dir": "ltr", "label": "RU", "name": "Русский"},
    {"code": "de", "file": "help.de.html", "dir": "ltr", "label": "DE", "name": "Deutsch"},
    {"code": "fr", "file": "help.fr.html", "dir": "ltr", "label": "FR", "name": "Français"},
    {"code": "es", "file": "help.es.html", "dir": "ltr", "label": "ES", "name": "Español"},
    {"code": "zh", "file": "help.zh.html", "dir": "ltr", "label": "中文", "name": "中文"},
    {"code": "ar", "file": "help.ar.html", "dir": "rtl", "label": "عربي", "name": "العربية"},
]

TOKEN_RE = re.compile(r"\{\{([a-zA-Z0-9_.@-]+)\}\}")


def _load_strings(code: str) -> dict[str, str]:
    path = STRINGS_DIR / f"{code}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a flat JSON object")
    bad = [k for k, v in data.items() if not isinstance(v, str)]
    if bad:
        raise ValueError(f"{path}: non-string values for keys {bad[:5]}")
    return data


def _lang_menu(current: str) -> str:
    items: list[str] = []
    for lang in LANGUAGES:
        aria = ' aria-current="page"' if lang["code"] == current else ""
        cls = "langlink current" if lang["code"] == current else "langlink"
        items.append(
            f'<a class="{cls}" href="/{lang["file"]}" hreflang="{lang["code"]}"'
            f' lang="{lang["code"]}" title="{lang["name"]}"{aria}>{lang["label"]}</a>'
        )
    return "".join(items)


def _alternate_links() -> str:
    lines = [
        f'<link rel="alternate" hreflang="{lang["code"]}" href="/{lang["file"]}">'
        for lang in LANGUAGES
    ]
    lines.append('<link rel="alternate" hreflang="x-default" href="/help.html">')
    return "\n".join(lines)


def render(template: str, lang: dict[str, str], strings: dict[str, str]) -> str:
    context = dict(strings)
    context["@lang"] = lang["code"]
    context["@dir"] = lang["dir"]
    context["@langmenu"] = _lang_menu(lang["code"])
    context["@alternates"] = _alternate_links()

    missing: set[str] = set()
    used: set[str] = set()

    def _sub(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in context:
            used.add(key)
            return context[key]
        missing.add(key)
        return match.group(0)

    rendered = TOKEN_RE.sub(_sub, template)
    if missing:
        raise KeyError(f"[{lang['code']}] template tokens without strings: {sorted(missing)[:20]} (total {len(missing)})")
    unused = set(strings) - used
    if unused:
        raise KeyError(f"[{lang['code']}] strings never used by the template: {sorted(unused)[:20]} (total {len(unused)})")
    leftover = TOKEN_RE.findall(rendered)
    if leftover:
        raise ValueError(f"[{lang['code']}] unresolved tokens after render: {leftover[:10]}")
    return rendered


def build() -> dict[str, str]:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    outputs: dict[str, str] = {}
    for lang in LANGUAGES:
        strings = _load_strings(lang["code"])
        outputs[lang["file"]] = render(template, lang, strings)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify committed pages match the template + strings")
    args = parser.parse_args()

    outputs = build()
    stale: list[str] = []
    for filename, content in outputs.items():
        target = OUTPUT_DIR / filename
        if args.check:
            if not target.exists() or target.read_text(encoding="utf-8") != content:
                stale.append(filename)
        else:
            target.write_text(content, encoding="utf-8", newline="\n")
            print(f"[help-pages] wrote {target.relative_to(ROOT_DIR)} ({len(content):,} bytes)")
    if args.check:
        if stale:
            print(f"[help-pages] STALE: {stale} — run `python scripts/build_help_pages.py` and commit.", file=sys.stderr)
            return 1
        print(f"[help-pages] OK: {len(outputs)} page(s) match the template + strings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
