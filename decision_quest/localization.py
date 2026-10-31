"""Question content localization; interface text stays in English.

Add a UTF-8 locales/<code>.json catalog and a LANGUAGES entry for new languages.
Missing translations fall back to the English catalog.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

LANGUAGES = [("English", "en"), ("Arabic — العربية", "ar"), ("German — Deutsch", "de")]


def normalize_language(language: str) -> str:
    return language if language in {code for _, code in LANGUAGES} else "en"


def _read_catalog(language: str) -> dict[str, Any]:
    return json.loads(
        (Path(__file__).parent / "locales" / f"{language}.json").read_text(encoding="utf-8")
    )


def _merge(base: dict[str, Any], translation: dict[str, Any]) -> dict[str, Any]:
    """Overlay translated fields while retaining nested English defaults."""
    result = {}
    for key in base.keys() | translation.keys():
        original = base.get(key)
        value = translation.get(key, original)
        result[key] = _merge(original, value) if isinstance(original, dict) and isinstance(value, dict) else value
    return result


@lru_cache
def catalog(language: str) -> dict[str, Any]:
    language = normalize_language(language)
    english = _read_catalog("en")
    return english if language == "en" else _merge(english, _read_catalog(language))


def direction_label(direction: str, language: str = "en") -> str:
    return catalog(language)["directions"][direction]


def localized_scene(scene: dict[str, Any], language: str) -> dict[str, Any]:
    language = normalize_language(language)
    content = catalog(language)["scenes"][scene["id"]]
    # Only text is loaded from catalogs; identifiers and answers stay in code.
    return {
        "id": scene["id"], "best": scene["best"], "language": language,
        **{key: content[key] for key in ("title", "goal", "story", "reason")},
        "paths": dict(content["paths"]),
    }
