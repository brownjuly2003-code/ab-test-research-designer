from __future__ import annotations

import json
import re
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Literal, Mapping

Language = Literal["en", "ru"]
SUPPORTED_LANGUAGES: tuple[Language, ...] = ("en", "ru")

_current_language: ContextVar[Language] = ContextVar("backend_language", default="en")
_translations = {
    language: json.loads((Path(__file__).with_name(f"{language}.json")).read_text(encoding="utf-8"))
    for language in SUPPORTED_LANGUAGES
}


def resolve_language(header_value: str | None) -> Language:
    if not header_value:
        return "en"

    ranked_languages: list[tuple[float, str]] = []
    for part in header_value.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        sections = [item.strip() for item in candidate.split(";") if item.strip()]
        locale = sections[0].lower().replace("_", "-")
        quality = 1.0
        for section in sections[1:]:
            if section.startswith("q="):
                try:
                    quality = float(section[2:])
                except ValueError:
                    quality = 1.0
        ranked_languages.append((quality, locale))

    ranked_languages.sort(key=lambda item: item[0], reverse=True)
    for _quality, locale in ranked_languages:
        primary = locale.split("-", 1)[0]
        if primary == "ru":
            return "ru"
        if primary == "en":
            return "en"

    return "en"


def set_current_language(language: Language) -> Token[Language]:
    return _current_language.set(language)


def reset_current_language(token: Token[Language]) -> None:
    _current_language.reset(token)


def get_current_language() -> Language:
    return _current_language.get()


def translate(
    key: str,
    variables: Mapping[str, object] | None = None,
    *,
    language: Language | None = None,
    fallback: str | None = None,
) -> str:
    value: object = _translations[language or get_current_language()]
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            return fallback or key
        value = value[part]

    if not isinstance(value, str):
        return fallback or key

    if not variables:
        return value

    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda match: str(variables.get(match.group(1), match.group(0))), value)
