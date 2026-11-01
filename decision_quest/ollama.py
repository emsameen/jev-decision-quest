"""Ollama System One requests and response validation."""

import time
from datetime import datetime, timezone
from typing import Any

import requests

from .config import AppSettings, DIRECTIONS
from .localization import LocalizationCatalog
from .models import Scenario


class ModelError(RuntimeError):
    """A model failure that the UI can report while keeping a round retryable."""


class OllamaClient:
    """Build and validate decision requests using this client's configuration."""

    def __init__(
        self, settings: AppSettings | None = None,
        localization: LocalizationCatalog | None = None,
    ):
        self.settings = settings if settings is not None else AppSettings.from_env()
        self.localization = localization if localization is not None else LocalizationCatalog()

    def build_payload(self, scene: Scenario) -> dict[str, Any]:
        """Build questions in the scenario language, preserving API identifiers."""
        questions = self.localization.catalog(scene.language)["questions"]
        payload = {
            "model": self.settings.model,
            "state": {
                "goal": scene.goal,
                "situation": scene.story,
                "paths": scene.paths,
            },
            "questions": {
                "route": {
                    "type": "choice",
                    "instructions": questions["route"],
                    "criteria": scene.paths,
                },
                "left_hazard": {
                    "type": "noul",
                    "instructions": questions["left_hazard"],
                },
                "left_risk": {
                    "type": "score",
                    "instructions": questions["left_risk"],
                    "criteria": questions["risk_criteria"],
                },
            },
        }
        return payload

    def _request(self, record: dict[str, Any]) -> tuple[dict[str, Any], float]:
        """Use the official Jev-style /v1/systemone endpoint; no chat prompting."""
        payload = record["request"]["json"]
        try:
            started = time.perf_counter()
            response = requests.post(
                self.settings.endpoint, json=payload, timeout=(10, self.settings.timeout)
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            record["status_code"] = response.status_code
            record["response"] = response.text
            try:
                record["response"] = response.json()
            except ValueError:
                pass
            response.raise_for_status()
            result = response.json()
            if result["answers"]["route"]["choice"] not in DIRECTIONS:
                raise ValueError("The response does not contain a valid route choice.")
            return result, elapsed_ms
        except requests.exceptions.ConnectionError as exc:
            raise ModelError(
                f"Cannot reach Ollama at {self.settings.ollama_url}. Start Ollama and run 'ollama pull {self.settings.model}'."
            ) from exc
        except requests.exceptions.HTTPError as exc:
            raise ModelError(
                f"Ollama returned an error: {response.status_code}. "
                f"Check that Ollama >= 0.35 is running and '{self.settings.model}' is installed. "
                f"Details: {response.text[:500]}"
            ) from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise ModelError(f"Unexpected model response: {exc}") from exc
        except requests.exceptions.Timeout as exc:
            raise ModelError(
                f"Ollama timed out after {self.settings.timeout:g} seconds. "
                "The model may still be loading or processing. "
                "Try again, or increase the OLLAMA_TIMEOUT environment variable."
            ) from exc

    def decide(
        self, scene: Scenario, *, debug: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any], float]:
        """Record the actual request, response, and failures for this session."""
        record = debug if debug is not None else {}
        record.update({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request": {
                "method": "POST", "url": self.settings.endpoint,
                "json": self.build_payload(scene),
            },
            "status_code": None, "response": None, "error": None,
        })
        started = time.perf_counter()
        try:
            return self._request(record)
        except Exception as exc:
            record["error"] = str(exc)
            raise
        finally:
            record["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
