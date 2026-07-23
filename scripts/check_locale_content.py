#!/usr/bin/env python
"""Locale *content* gate — catch mojibake and replacement characters in catalogs.

This script is a **value** scanner only: it does not enforce leaf-key parity
across locales (that is a separate concern — frontend unit coverage /
manual parity when adding keys). It looks *inside* translation strings so
es/de mojibake (accents/Greek letters stored as ``?``) cannot sit unnoticed
the way it did until the 2026-06-17 audit. Scanned catalogs:

* ``app/frontend/public/locales/*.json`` (frontend bundles)
* ``app/backend/app/i18n/*.json``         (backend export/report catalogs)

Failure conditions:

1. **Replacement character** ``U+FFFD`` (``�``) anywhere — the canonical
   "this byte could not be decoded" marker.
2. **Mojibake question mark** — a ``?`` sandwiched between two word characters
   (Latin incl. Latin-1 accents, Cyrillic, CJK, Arabic). When an accented or
   non-ASCII glyph is lost in a bad round-trip it collapses to ``?`` *inside* a
   word (e.g. ``Français`` -> ``Fran?ais``, ``Francés`` -> ``Franc?s``).

Genuine question marks are not flagged: a real interrogative ``?`` closes a
clause and is followed by whitespace / punctuation / end-of-string, never by a
word character, so it never matches the sandwiched pattern. Spanish ``¿…?`` and
trailing ``…?`` are covered by the same reasoning. URL query strings
(``…?lang=en``) and ``scheme://`` tokens are whitelisted explicitly because a
``?`` there is structural, not lost text.

Usage::

    python scripts/check_locale_content.py            # scan, exit 1 on violations
    python scripts/check_locale_content.py --self-test # prove the detector works
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
LOCALE_DIRS = (
    ROOT_DIR / "app" / "frontend" / "public" / "locales",
    ROOT_DIR / "app" / "backend" / "app" / "i18n",
)

REPLACEMENT_CHAR = "�"

# Word characters across every script the project ships: ASCII + Latin-1
# accented letters, Cyrillic, CJK unified ideographs, Arabic.
_WORD = r"[A-Za-zÀ-ÿЀ-ӿ一-鿿؀-ۿ]"
# A '?' flanked by word characters on both sides == lost glyph, not a question.
MOJIBAKE_QMARK = re.compile(_WORD + r"\?" + _WORD)
# Structural '?' that must NOT be treated as mojibake even when flanked by
# letters: a query string (?key=...) immediately following the '?'.
_QUERY_STRING = re.compile(r"\?[A-Za-z0-9_]+=")


class Violation:
    __slots__ = ("path", "key", "kind", "value", "fragment")

    def __init__(self, path: Path, key: str, kind: str, value: str, fragment: str) -> None:
        self.path = path
        self.key = key
        self.kind = kind
        self.value = value
        self.fragment = fragment

    def render(self) -> str:
        try:
            rel: Path | str = self.path.relative_to(ROOT_DIR)
        except ValueError:
            rel = self.path
        return f"  {rel} :: {self.key}\n      {self.kind}: {self.fragment!r}  in  {self.value!r}"


def _token_around(value: str, index: int) -> str:
    """Maximal run of non-whitespace characters containing position *index*."""
    start = index
    while start > 0 and not value[start - 1].isspace():
        start -= 1
    end = index
    while end < len(value) and not value[end].isspace():
        end += 1
    return value[start:end]


def _qmark_is_structural(value: str, index: int) -> bool:
    token = _token_around(value, index)
    if "://" in token:
        return True
    # query string: the '?' is followed by `name=`
    if _QUERY_STRING.match(value[index:]):
        return True
    return False


def find_violations_in_string(key: str, value: str, path: Path) -> list[Violation]:
    out: list[Violation] = []
    if REPLACEMENT_CHAR in value:
        idx = value.index(REPLACEMENT_CHAR)
        out.append(Violation(path, key, "U+FFFD replacement char", value, value[max(0, idx - 8) : idx + 9]))
    for match in MOJIBAKE_QMARK.finditer(value):
        qmark_index = match.start() + 1
        if _qmark_is_structural(value, qmark_index):
            continue
        out.append(Violation(path, key, "mojibake '?'", value, match.group(0)))
    return out


def _walk(node: object, key_path: list[str], path: Path, out: list[Violation]) -> None:
    if isinstance(node, dict):
        for key, child in node.items():
            _walk(child, key_path + [str(key)], path, out)
    elif isinstance(node, list):
        for index, child in enumerate(node):
            _walk(child, key_path + [str(index)], path, out)
    elif isinstance(node, str):
        out.extend(find_violations_in_string(".".join(key_path), node, path))


def scan_file(path: Path) -> list[Violation]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[Violation] = []
    _walk(data, [], path, out)
    return out


def scan_all() -> tuple[list[Violation], int]:
    violations: list[Violation] = []
    file_count = 0
    for directory in LOCALE_DIRS:
        for path in sorted(directory.glob("*.json")):
            file_count += 1
            violations.extend(scan_file(path))
    return violations, file_count


def self_test() -> int:
    """Prove the detector flags real mojibake and leaves genuine text alone."""
    fake = Path("<self-test>")
    must_flag = {
        "mojibake mid-word (Francés)": "Franc?s",
        "mojibake (Français)": "Fran?ais",
        "replacement char": "r�sumo",
        "cyrillic mojibake": "ма?ина",
    }
    must_pass = {
        "genuine question": "¿Estás seguro?",
        "trailing ellipsis question": "Continuer…?",
        "url query string": "Open https://x.com/path?lang=en now",
        "clean accented": "Français · Diseñador · 测试 · اختبار",
        "ascii sentence": "Ship or do not ship?",
    }
    failures: list[str] = []
    for label, sample in must_flag.items():
        if not find_violations_in_string("k", sample, fake):
            failures.append(f"FAILED to flag mojibake: {label} ({sample!r})")
    for label, sample in must_pass.items():
        hits = find_violations_in_string("k", sample, fake)
        if hits:
            failures.append(f"FALSE POSITIVE on clean text: {label} ({sample!r}) -> {hits[0].fragment!r}")
    if failures:
        print("[locale-content] self-test FAILED:", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(f"[locale-content] self-test passed ({len(must_flag)} flagged, {len(must_pass)} clean).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Verify the detector flags injected mojibake and passes clean text, then exit.",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    violations, file_count = scan_all()
    if violations:
        print(f"[locale-content] FAILED: {len(violations)} content violation(s) across locale catalogs:", file=sys.stderr)
        for violation in violations:
            print(violation.render(), file=sys.stderr)
        print(
            "\nThese look like lost/garbled characters (mojibake or undecodable bytes), "
            "not genuine punctuation. Repair the source string in UTF-8.",
            file=sys.stderr,
        )
        return 1

    print(f"[locale-content] OK: {file_count} locale file(s) clean (no mojibake, no U+FFFD).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
