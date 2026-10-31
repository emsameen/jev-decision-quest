"""Ollama System One requests and response validation."""

import time
from datetime import datetime, timezone
from typing import Any

import gradio as gr
import requests

from .config import DIRECTIONS, MODEL, OLLAMA_TIMEOUT, OLLAMA_URL
from .localization import catalog


def build_payload(scene: dict[str, Any]) -> dict[str, Any]:
    """Build questions in the scenario language, preserving API identifiers."""
    questions = catalog(scene.get("language", "en"))["questions"]
    payload = {
        "model": MODEL,
        "state": {
            "goal": scene["goal"],
            "situation": scene["story"],
            "paths": scene["paths"],
        },
        "questions": {
            "route": {
                "type": "choice",
                "instructions": questions["route"],
                "criteria": scene["paths"],
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


def _call_model(scene: dict[str, Any], record: dict[str, Any]) -> tuple[dict[str, Any], float]:
    """Use the official Jev-style /v1/systemone endpoint; no chat prompting."""
    payload = record["request"]["json"]
    try:
        started = time.perf_counter()
        response = requests.post(
            f"{OLLAMA_URL}/v1/systemone", json=payload, timeout=(10, OLLAMA_TIMEOUT)
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
        raise gr.Error(
            f"Cannot reach Ollama at {OLLAMA_URL}. Start Ollama and run 'ollama pull {MODEL}'."
        ) from exc
    except requests.exceptions.HTTPError as exc:
        raise gr.Error(
            f"Ollama returned an error: {response.status_code}. "
            f"Check that Ollama >= 0.35 is running and '{MODEL}' is installed. "
            f"Details: {response.text[:500]}"
        ) from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise gr.Error(f"Unexpected model response: {exc}") from exc
    except requests.exceptions.Timeout as exc:
        raise gr.Error(
            f"Ollama timed out after {OLLAMA_TIMEOUT:g} seconds. "
            "The model may still be loading or processing. "
            "Try again, or increase the OLLAMA_TIMEOUT environment variable."
        ) from exc


def call_model(
    scene: dict[str, Any], *, debug: dict[str, Any] | None = None
) -> tuple[dict[str, Any], float]:
    """Record the actual request, response, and failures for this session."""
    record = debug if debug is not None else {}
    record.update({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request": {
            "method": "POST", "url": f"{OLLAMA_URL}/v1/systemone",
            "json": build_payload(scene),
        },
        "status_code": None, "response": None, "error": None,
    })
    started = time.perf_counter()
    try:
        return _call_model(scene, record)
    except Exception as exc:
        record["error"] = str(exc)
        raise
    finally:
        record["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
