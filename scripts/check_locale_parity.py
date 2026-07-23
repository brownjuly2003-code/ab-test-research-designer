#!/usr/bin/env python
"""Locale key parity + static key-usage gate for frontend catalogs.

``en.json`` is the source of truth for required semantic keys. Other shipped
locales must cover every English key. i18next plural forms are language-
specific (``_one``/``_other`` vs ``_few``/``_many``, bare fallback keys for
CJK/Arabic catalogs), so coverage is evaluated at the **plural family** level:

* a family is covered when the locale has the bare base key **or** any CLDR
  plural suffix form of that base;
* non-plural leaf keys must exist verbatim;
* stale extras that are not plural variants of an English family fail the gate.

Additionally, static ``t("…")`` / ``t('…')`` call sites under
``app/frontend/src`` must resolve against ``en.json`` (with plural family
fallback), so a deleted catalog key cannot leave hardcoded English in code
without failing CI.

Usage::

    python scripts/check_locale_parity.py            # scan, exit 1 on violations
    python scripts/check_locale_parity.py --self-test # prove detector works
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_LOCALE_DIR = ROOT_DIR / "app" / "frontend" / "public" / "locales"
FRONTEND_SRC_DIR = ROOT_DIR / "app" / "frontend" / "src"
REFERENCE_LOCALE = "en"
SHIPPED_LOCALES = ("en", "ru", "de", "es", "fr", "zh", "ar")

PLURAL_SUFFIX_RE = re.compile(r"_(zero|one|two|few|many|other)$")
# Static call sites: t("a.b"), t('a.b'), i18n.t("a.b") — skip template literals.
T_CALL_RE = re.compile(
    r"""(?:\b(?:t|i18n\.t)\s*\(\s*)(?P<quote>['"])(?P<key>[^'"`]+?)(?P=quote)"""
)
SRC_GLOBS = ("**/*.ts", "**/*.tsx")


def flatten_leaves(node: object, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    if isinstance(node, dict):
        for key, child in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            out.update(flatten_leaves(child, path))
    elif isinstance(node, list):
        for index, child in enumerate(node):
            path = f"{prefix}[{index}]"
            out.update(flatten_leaves(child, path))
    else:
        out[prefix] = node
    return out


def plural_base(key: str) -> str | None:
    match = PLURAL_SUFFIX_RE.search(key)
    if not match:
        return None
    return key[: match.start()]


def family_members(keys: set[str], base: str) -> set[str]:
    members = {key for key in keys if key == base or plural_base(key) == base}
    return members


def load_locale_leaves(path: Path) -> dict[str, object]:
    return flatten_leaves(json.loads(path.read_text(encoding="utf-8")))


def check_parity(locale_dir: Path) -> list[str]:
    """Return human-readable violations for frontend locale parity."""
    errors: list[str] = []
    reference_path = locale_dir / f"{REFERENCE_LOCALE}.json"
    if not reference_path.is_file():
        return [f"missing reference locale {reference_path}"]

    reference = load_locale_leaves(reference_path)
    ref_keys = set(reference)
    ref_plural_bases = {base for key in ref_keys if (base := plural_base(key))}
    ref_non_plural = {key for key in ref_keys if plural_base(key) is None}

    for locale in SHIPPED_LOCALES:
        path = locale_dir / f"{locale}.json"
        if not path.is_file():
            errors.append(f"missing shipped locale file: {path.name}")
            continue
        if locale == REFERENCE_LOCALE:
            continue

        leaves = load_locale_leaves(path)
        keys = set(leaves)

        for key in sorted(ref_non_plural - keys):
            # Bare key may be the English non-plural form of a plural family
            # that this locale only ships as plural forms — allow if family covered.
            if key in ref_plural_bases and family_members(keys, key):
                continue
            errors.append(f"{path.name}: missing key {key}")

        for base in sorted(ref_plural_bases):
            if not family_members(keys, base):
                errors.append(f"{path.name}: missing plural family {base}")

        for key in sorted(keys - ref_keys):
            base = plural_base(key)
            if base and base in ref_plural_bases:
                continue
            if key in ref_plural_bases:
                continue
            errors.append(f"{path.name}: stale key not in {REFERENCE_LOCALE}.json: {key}")

    return errors


def key_exists_in_catalog(key: str, catalog_keys: set[str], plural_bases: set[str]) -> bool:
    if key in catalog_keys:
        return True
    base = plural_base(key)
    if base is not None:
        return bool(family_members(catalog_keys, base))
    if key in plural_bases:
        return bool(family_members(catalog_keys, key))
    return False


def extract_t_keys(src_dir: Path) -> set[str]:
    found: set[str] = set()
    for pattern in SRC_GLOBS:
        for path in src_dir.glob(pattern):
            if "node_modules" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for match in T_CALL_RE.finditer(text):
                key = match.group("key").strip()
                # Dynamic suffixes / empty / interpolation left for runtime.
                if not key or "${" in key or key.endswith("."):
                    continue
                found.add(key)
    return found


def check_key_usage(src_dir: Path, locale_dir: Path) -> list[str]:
    reference_path = locale_dir / f"{REFERENCE_LOCALE}.json"
    if not reference_path.is_file():
        return [f"missing reference locale {reference_path}"]

    catalog_keys = set(load_locale_leaves(reference_path))
    plural_bases = {base for key in catalog_keys if (base := plural_base(key))}
    errors: list[str] = []
    for key in sorted(extract_t_keys(src_dir)):
        if not key_exists_in_catalog(key, catalog_keys, plural_bases):
            errors.append(f"src t() key missing from {REFERENCE_LOCALE}.json: {key}")
    return errors


def self_test() -> int:
    with tempfile.TemporaryDirectory() as raw:
        locale_dir = Path(raw) / "locales"
        src_dir = Path(raw) / "src"
        locale_dir.mkdir()
        src_dir.mkdir()

        en = {
            "app": {"title": "Title"},
            "items": {"count_one": "1 item", "count_other": "{{count}} items"},
            "plain": "ok",
        }
        (locale_dir / "en.json").write_text(json.dumps(en), encoding="utf-8")

        # de: full parity
        (locale_dir / "de.json").write_text(json.dumps(en), encoding="utf-8")
        # ru: language-specific plural forms + bare plain
        ru = {
            "app": {"title": "Заголовок"},
            "items": {
                "count_one": "1",
                "count_few": "few",
                "count_many": "many",
                "count_other": "other",
            },
            "plain": "ok",
        }
        (locale_dir / "ru.json").write_text(json.dumps(ru), encoding="utf-8")
        # zh: bare plural fallback
        zh = {
            "app": {"title": "标题"},
            "items": {"count": "{{count}}"},
            "plain": "ok",
        }
        (locale_dir / "zh.json").write_text(json.dumps(zh), encoding="utf-8")
        # remaining shipped locales copy en for the self-test fixture
        for name in SHIPPED_LOCALES:
            path = locale_dir / f"{name}.json"
            if not path.exists():
                path.write_text(json.dumps(en), encoding="utf-8")

        parity_ok = check_parity(locale_dir)
        if parity_ok:
            print("[locale-parity] self-test FAILED: clean fixture flagged:", parity_ok, file=sys.stderr)
            return 1

        # missing key must fail
        broken = json.loads((locale_dir / "de.json").read_text(encoding="utf-8"))
        del broken["plain"]
        (locale_dir / "de.json").write_text(json.dumps(broken), encoding="utf-8")
        parity_bad = check_parity(locale_dir)
        if not any("missing key plain" in item for item in parity_bad):
            print("[locale-parity] self-test FAILED: missing key not flagged", file=sys.stderr)
            return 1
        # restore de
        (locale_dir / "de.json").write_text(json.dumps(en), encoding="utf-8")

        # stale key must fail
        stale = json.loads((locale_dir / "de.json").read_text(encoding="utf-8"))
        stale["orphan"] = "x"
        (locale_dir / "de.json").write_text(json.dumps(stale), encoding="utf-8")
        parity_stale = check_parity(locale_dir)
        if not any("stale key" in item and "orphan" in item for item in parity_stale):
            print("[locale-parity] self-test FAILED: stale key not flagged", file=sys.stderr)
            return 1
        (locale_dir / "de.json").write_text(json.dumps(en), encoding="utf-8")

        # key-usage: present key OK, missing key fails
        (src_dir / "ok.tsx").write_text('const x = t("app.title");\n', encoding="utf-8")
        usage_ok = check_key_usage(src_dir, locale_dir)
        if usage_ok:
            print("[locale-parity] self-test FAILED: valid t() key flagged:", usage_ok, file=sys.stderr)
            return 1
        (src_dir / "bad.tsx").write_text('const y = t("does.not.exist");\n', encoding="utf-8")
        usage_bad = check_key_usage(src_dir, locale_dir)
        if not any("does.not.exist" in item for item in usage_bad):
            print("[locale-parity] self-test FAILED: missing t() key not flagged", file=sys.stderr)
            return 1

        # plural family usage: t("items.count") should resolve via family
        (src_dir / "plural.tsx").write_text('const z = t("items.count", { count: 2 });\n', encoding="utf-8")
        # remove bad file so only plural remains with ok
        (src_dir / "bad.tsx").unlink()
        usage_plural = check_key_usage(src_dir, locale_dir)
        if usage_plural:
            print(
                "[locale-parity] self-test FAILED: plural family t() key flagged:",
                usage_plural,
                file=sys.stderr,
            )
            return 1

    print("[locale-parity] self-test passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--locale-dir", default=str(FRONTEND_LOCALE_DIR))
    parser.add_argument("--src-dir", default=str(FRONTEND_SRC_DIR))
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    locale_dir = Path(args.locale_dir)
    src_dir = Path(args.src_dir)
    errors = check_parity(locale_dir) + check_key_usage(src_dir, locale_dir)
    if errors:
        print(f"[locale-parity] {len(errors)} violation(s):", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    locale_count = sum(1 for name in SHIPPED_LOCALES if (locale_dir / f"{name}.json").is_file())
    t_keys = len(extract_t_keys(src_dir))
    print(
        f"[locale-parity] OK: {locale_count} frontend locales; "
        f"{t_keys} static t() keys resolve against {REFERENCE_LOCALE}.json"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
