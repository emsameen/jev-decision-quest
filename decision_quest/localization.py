"""Question catalogs with per-instance caching and English fallback."""

import json
from pathlib import Path
from typing import Any

from .models import Scenario, SceneRule

LANGUAGES = [("English", "en"), ("Arabic — العربية", "ar"), ("German — Deutsch", "de")]


class LocalizationCatalog:
    """Load authored question text without changing game rules or API keys."""

    def __init__(self, locale_dir: Path | None = None):
        self.locale_dir = locale_dir if locale_dir is not None else Path(__file__).parent / "locales"
        self._catalogs: dict[str, dict[str, Any]] = {}

    @staticmethod
    def normalize_language(language: str) -> str:
        return language if language in {code for _, code in LANGUAGES} else "en"

    def _read_catalog(self, language: str) -> dict[str, Any]:
        return json.loads((self.locale_dir / f"{language}.json").read_text(encoding="utf-8"))

    @classmethod
    def _merge(cls, base: dict[str, Any], translation: dict[str, Any]) -> dict[str, Any]:
        """Overlay translated fields while retaining nested English defaults."""
        result = {}
        for key in base.keys() | translation.keys():
            original = base.get(key)
            value = translation.get(key, original)
            result[key] = (
                cls._merge(original, value)
                if isinstance(original, dict) and isinstance(value, dict) else value
            )
        return result

    def catalog(self, language: str) -> dict[str, Any]:
        language = self.normalize_language(language)
        if "en" not in self._catalogs:
            self._catalogs["en"] = self._read_catalog("en")
        if language not in self._catalogs:
            self._catalogs[language] = self._merge(
                self._catalogs["en"], self._read_catalog(language)
            )
        return self._catalogs[language]

    def direction_label(self, direction: str, language: str = "en") -> str:
        return self.catalog(language)["directions"][direction]

    def localize(self, rule: SceneRule, language: str) -> Scenario:
        language = self.normalize_language(language)
        content = self.catalog(language)["scenes"][rule.id]
        return Scenario(
            id=rule.id, best=rule.best, language=language,
            **{key: content[key] for key in ("title", "goal", "story", "reason")},
            paths=dict(content["paths"]),
        )
