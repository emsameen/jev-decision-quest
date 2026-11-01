"""Application settings and shared game constants."""

import os
from dataclasses import dataclass

ROUNDS = 5
DIRECTIONS = ("left", "middle", "right")


@dataclass(frozen=True)
class AppSettings:
    """Configuration owned by an application rather than global import state."""

    ollama_url: str = "http://localhost:11434"
    model: str = "d3:4b"
    timeout: float = 300
    rounds: int = ROUNDS

    @classmethod
    def from_env(cls) -> "AppSettings":
        return cls(
            ollama_url=os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
            model=os.environ.get("OLLAMA_MODEL", "d3:4b"),
            timeout=float(os.environ.get("OLLAMA_TIMEOUT", "300")),
        )

    @property
    def endpoint(self) -> str:
        return f"{self.ollama_url.rstrip('/')}/v1/systemone"
