"""Gradio event controller for session rules, model calls, and presentation."""

import random
from typing import Any

import gradio as gr

from .config import AppSettings, DIRECTIONS
from .models import GameSession
from .ollama import ModelError, OllamaClient
from .presentation import GamePresenter
from .scenes import SceneRepository


class GameController:
    """Coordinate a round without storing player state on this shared object."""

    def __init__(
        self, settings: AppSettings, scenes: SceneRepository,
        client: OllamaClient, presenter: GamePresenter,
    ):
        if not 1 <= settings.rounds <= len(scenes):
            raise ValueError(f"Round count must be between 1 and {len(scenes)}.")
        self.settings = settings
        self.scenes = scenes
        self.client = client
        self.presenter = presenter
        self.localization = scenes.localization

    def _ready_round(self, game: GameSession) -> tuple[Any, ...]:
        scene = self.scenes.current(game)
        return (
            game,
            self.presenter.scene_markdown(game),
            gr.update(choices=self.presenter.option_choices(scene), value=None, interactive=True),
            self.presenter.scoreboard(game)
            + "\n\n**Your turn:** Choose the route you think best protects the goal.",
            '<div class="quest-empty"><p>Choose your route, then run the model '
            'to reveal its decision breakdown.</p></div>',
            self.presenter.debug_summary_markdown(game.debug),
            game.debug,
            gr.update(interactive=False),
            gr.update(interactive=False),
        )

    def start_game(self, language: str = "en") -> tuple[Any, ...]:
        game = GameSession.start(
            random.sample(range(len(self.scenes)), self.settings.rounds),
            self.localization.normalize_language(language),
        )
        return self._ready_round(game)

    def resolve_round(
        self, game: GameSession | None, user_choice: str | None,
    ) -> tuple[Any, ...]:
        if game is None:
            gr.Info("Click Start Game to begin a new game.")
            return (gr.skip(),) * 9
        try:
            game.require_unresolved_round()
        except ValueError as exc:
            gr.Info(str(exc))
            return (gr.skip(),) * 9
        if user_choice not in DIRECTIONS:
            gr.Info("Choose one of the three routes before running the model.")
            return (gr.skip(),) * 9

        scene = self.scenes.current(game)
        language = game.language
        record = {
            "round": game.round + 1,
            "player_choice": user_choice,
            "player_choice_label": self.localization.direction_label(user_choice, language),
            "matched_model": None,
            "reasoning": {
                "correct_route": scene.best,
                "correct_route_label": self.localization.direction_label(scene.best, language),
                "explanation": scene.reason,
                "source": "fixed game rules",
            },
        }
        game.debug.append(record)
        try:
            result, elapsed_ms = self.client.decide(scene, debug=record)
        except ModelError as exc:
            record["error"] = str(exc)
            return (
                game, gr.skip(), gr.skip(), str(exc), gr.skip(),
                self.presenter.debug_summary_markdown(game.debug), game.debug,
                gr.skip(), gr.skip(),
            )

        decision = result["answers"]["route"]
        model_choice = decision["choice"]
        record["model_choice"] = model_choice
        record["matched_model"] = user_choice == model_choice
        game.score_round(user_choice, model_choice, scene.best)
        event = (
            f"**Your route:** {self.localization.direction_label(user_choice, language)} · "
            f"**Model's route:** {self.localization.direction_label(model_choice, language)} · "
            f"**Agreement:** {'matched' if user_choice == model_choice else 'different'}"
        )
        confidence = decision.get("confidence")
        conf_text = (
            f" · concentration score {confidence:.2f}"
            if isinstance(confidence, (float, int)) else ""
        )
        info = (
            self.presenter.scoreboard(game)
            + f"\n\n{event}\n\n**Fixed-rule answer:** "
            + f"{self.localization.direction_label(scene.best, language)} — {scene.reason}\n\n"
            + f"**Inference:** {elapsed_ms:.0f} ms{conf_text}"
        )
        return (
            game,
            self.presenter.scene_markdown(game),
            gr.update(interactive=False),
            info,
            self.presenter.decision_breakdown_html(result.get("answers", {}), model_choice, language),
            self.presenter.debug_summary_markdown(game.debug),
            game.debug,
            gr.update(interactive=False),
            gr.update(interactive=True),
        )

    def next_round(self, game: GameSession | None) -> tuple[Any, ...]:
        if game is None:
            gr.Info("Click Start Game to begin a new game.")
            return (gr.skip(),) * 9
        try:
            game.advance()
        except ValueError as exc:
            gr.Info(str(exc))
            return (gr.skip(),) * 9
        if not game.active:
            final = (
                f"### 🏁 Game finished\n\n{self.presenter.scoreboard(game)}\n\n"
                "You've seen how route choices, yes/no estimates, and rubric scores work. "
                "Press **Start Game** to play another set of scenarios."
            )
            return (
                game, final, gr.update(interactive=False),
                "**Session completed.** Review the round summaries or inspect the raw traces.",
                "", self.presenter.debug_summary_markdown(game.debug), game.debug,
                gr.update(interactive=False), gr.update(interactive=False),
            )
        return self._ready_round(game)

    @staticmethod
    def select_route(choice: str | None) -> dict[str, Any]:
        return gr.update(interactive=choice in DIRECTIONS)

    @staticmethod
    def toggle_debug(visible: bool) -> dict[str, Any]:
        return gr.update(visible=visible)
