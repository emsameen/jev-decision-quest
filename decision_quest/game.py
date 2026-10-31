"""Game lifecycle, scoring, and Gradio event handlers."""

import random
from typing import Any

import gradio as gr

from .config import DIRECTIONS, ROUNDS
from .localization import direction_label, normalize_language
from .ollama import call_model
from .presentation import (
    debug_summary_markdown, decision_breakdown_html, option_choices, scene_markdown, scoreboard,
)
from .scenes import SCENES, current_scene


def start_game(language: str = "en"):
    game = {
        "active": True,
        "debug": [],
        "round": 0,
        "order": random.sample(range(len(SCENES)), ROUNDS),
        "player": 0,
        "model": 0,
        "matches": 0,
        "resolved": False,
        "language": normalize_language(language),
    }
    scene = current_scene(game)
    return (
        game,
        scene_markdown(game),
        gr.update(choices=option_choices(scene), value=None,
                  interactive=True),
        scoreboard(game) + "\n\n**Your turn:** Choose the route you think best protects the goal.",
        "_Decision breakdown will appear after you run the model._",
        debug_summary_markdown([]),
        [],
        gr.update(interactive=False),
        gr.update(interactive=False),
    )


def resolve_round(game: dict[str, Any], user_choice: str | None):
    if not game or not game.get("active"):
        gr.Info("Click Start Game to begin a new game.")
        return (gr.skip(),) * 9
    if game.get("resolved"):
        gr.Info("This round is complete. Click Next Round to continue.")
        return (gr.skip(),) * 9
    if user_choice not in DIRECTIONS:
        gr.Info("Choose one of the three routes before running the model.")
        return (gr.skip(),) * 9

    scene = current_scene(game)
    language = game.get("language", "en")
    record = {
        "round": game["round"] + 1,
        "player_choice": user_choice,
        "player_choice_label": direction_label(user_choice, language),
        "matched_model": None,
        "reasoning": {
            "correct_route": scene["best"],
            "correct_route_label": direction_label(scene["best"], language),
            "explanation": scene["reason"],
            "source": "fixed game rules",
        },
    }
    game.setdefault("debug", []).append(record)
    try:
        result, elapsed_ms = call_model(scene, debug=record)
    except gr.Error as exc:
        record["error"] = str(exc)
        return (
            game, gr.skip(), gr.skip(), str(exc), gr.skip(),
            debug_summary_markdown(game["debug"]), game["debug"], gr.skip(), gr.skip(),
        )
    decision = result["answers"]["route"]
    model_choice = decision["choice"]
    record["model_choice"] = model_choice
    record["matched_model"] = user_choice == model_choice
    correct = scene["best"]

    if user_choice == correct:
        game["player"] += 1
    if model_choice == correct:
        game["model"] += 1
    if user_choice == model_choice:
        game["matches"] += 1
    event = (
        f"**Your route:** {direction_label(user_choice, language)} · "
        f"**Model's route:** {direction_label(model_choice, language)} · "
        f"**Agreement:** {'matched' if user_choice == model_choice else 'different'}"
    )

    game["resolved"] = True
    confidence = decision.get("confidence")
    conf_text = f" · concentration score {confidence:.2f}" if isinstance(confidence, (float, int)) else ""
    info = (
        scoreboard(game)
        + f"\n\n{event}\n\n**Fixed-rule answer:** {direction_label(correct, language)} — {scene['reason']}\n\n"
        + f"**Inference:** {elapsed_ms:.0f} ms{conf_text}"
    )
    return (
        game,
        scene_markdown(game),
        gr.update(interactive=False),
        info,
        decision_breakdown_html(result.get("answers", {}), model_choice, language),
        debug_summary_markdown(game["debug"]),
        game["debug"],
        gr.update(interactive=False),
        gr.update(interactive=True),
    )


def next_round(game: dict[str, Any]):
    if not game or not game.get("active"):
        gr.Info("Click Start Game to begin a new game.")
        return (gr.skip(),) * 9
    if not game.get("resolved"):
        gr.Info("Choose a route and run the model to finish this round first.")
        return (gr.skip(),) * 9
    if game["round"] >= ROUNDS - 1:
        game["active"] = False
        final = (
            f"### 🏁 Game finished\n\n{scoreboard(game)}\n\n"
            + (
                "You've seen how route choices, yes/no estimates, and rubric scores work. "
                "Press **Start Game** to play another set of scenarios."
            )
        )
        return (
            game, final, gr.update(interactive=False),
            "**Session completed.** Review the round summaries or inspect the raw traces.",
            "", debug_summary_markdown(game.get("debug", [])), game.get("debug", []),
            gr.update(interactive=False), gr.update(interactive=False),
        )
    game["round"] += 1
    game["resolved"] = False
    scene = current_scene(game)
    return (
        game,
        scene_markdown(game),
        gr.update(choices=option_choices(scene), value=None,
                  interactive=True),
        scoreboard(game) + "\n\n**Your turn:** Choose the route you think best protects the goal.",
        "_Decision breakdown will appear after you run the model._",
        debug_summary_markdown(game.get("debug", [])), game.get("debug", []),
        gr.update(interactive=False), gr.update(interactive=False),
    )
