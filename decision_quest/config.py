"""Environment settings and game constants."""

import os

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
MODEL = os.environ.get("OLLAMA_MODEL", "d3:4b")
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "300"))
ROUNDS = 5
DIRECTIONS = ("left", "middle", "right")
MODE_PREDICT = "Predict Nimble"
MODE_DUEL = "Human vs Nimble"
MODE_WATCH = "Watch Nimble"
