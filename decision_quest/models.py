"""Scenario values and the state and rules of one player's game."""

from dataclasses import dataclass, field
from typing import Any

from .config import DIRECTIONS


@dataclass(frozen=True)
class SceneRule:
    id: str
    best: str


@dataclass(frozen=True)
class Scenario:
    id: str
    best: str
    language: str
    title: str
    goal: str
    story: str
    reason: str
    paths: dict[str, str]


@dataclass
class GameSession:
    """Mutable state kept in gr.State, never on the shared controller."""

    active: bool = False
    debug: list[dict[str, Any]] = field(default_factory=list)
    round: int = 0
    order: list[int] = field(default_factory=list)
    player: int = 0
    model: int = 0
    matches: int = 0
    resolved: bool = False
    language: str = "en"

    @classmethod
    def start(cls, order: list[int], language: str = "en") -> "GameSession":
        if not order or len(set(order)) != len(order):
            raise ValueError("A game requires a nonempty order of distinct scenarios.")
        return cls(active=True, order=list(order), language=language)

    @property
    def total_rounds(self) -> int:
        return len(self.order)

    @property
    def completed_rounds(self) -> int:
        return self.round + int(self.resolved)

    def require_unresolved_round(self) -> None:
        if not self.active:
            raise ValueError("Click Start Game to begin a new game.")
        if self.resolved:
            raise ValueError("This round is complete. Click Next Round to continue.")

    def score_round(self, player_choice: str, model_choice: str, correct: str) -> None:
        """Apply a decision once, after inference has succeeded."""
        self.require_unresolved_round()
        if any(choice not in DIRECTIONS for choice in (player_choice, model_choice, correct)):
            raise ValueError("Route choices must be left, middle, or right.")
        self.player += int(player_choice == correct)
        self.model += int(model_choice == correct)
        self.matches += int(player_choice == model_choice)
        self.resolved = True

    def advance(self) -> None:
        if not self.active:
            raise ValueError("Click Start Game to begin a new game.")
        if not self.resolved:
            raise ValueError("Choose a route and run the model to finish this round first.")
        if self.round == self.total_rounds - 1:
            self.active = False
        else:
            self.round += 1
            self.resolved = False
