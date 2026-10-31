"""Game lifecycle, scoring, and Gradio event handlers."""

import random
from typing import Any

import gradio as gr

from .config import DIRECTIONS, MODE_DUEL, MODE_PREDICT, MODE_WATCH, ROUNDS
from .localization import direction_label, normalize_language
from .ollama import call_nimble
from .presentation import option_choices, probability_html, scene_markdown, scoreboard
from .scenes import SCENES, current_scene


def start_game(mode: str, language: str = "en"):
    game = {
        "active": True,
        "debug": [],
        "round": 0,
        "order": random.sample(range(len(SCENES)), ROUNDS),
        "player": 0,
        "nimble": 0,
        "resolved": False,
        "mode": mode,
        "language": normalize_language(language),
    }
    scene = current_scene(game)
    hint = (
        "**Watch mode:** Click *Ask Nimble* to reveal its decision."
        if mode == MODE_WATCH
        else "**Your turn:** Choose a route, then click *Ask Nimble*."
    )
    return (
        game,
        scene_markdown(game),
        gr.update(choices=option_choices(scene), value=None,
                  interactive=(mode != MODE_WATCH)),
        scoreboard(game, mode) + "\n\n" + hint,
        "_Probabilities will appear after a model decision._",
        [],
        gr.update(interactive=True),
        gr.update(interactive=False),
    )


def resolve_round(game: dict[str, Any], mode: str, user_choice: str | None):
    if not game or not game.get("active"):
        gr.Info("Click Start Game to begin a new game.")
        return (gr.skip(),) * 8
    if game.get("resolved"):
        gr.Info("This round is complete. Click Next Round to continue.")
        return (gr.skip(),) * 8
    mode = game["mode"]  # Mode is fixed at Start Game, even if the selector changes.
    if mode != MODE_WATCH and user_choice not in DIRECTIONS:
        raise gr.Error("Select one of the three routes before asking Nimble.")

    scene = current_scene(game)
    record = {"round": game["round"] + 1}
    game.setdefault("debug", []).append(record)
    try:
        result, elapsed_ms = call_nimble(scene, debug=record)
    except gr.Error as exc:
        record["error"] = str(exc)
        return (
            game, gr.skip(), gr.skip(), str(exc), gr.skip(),
            game["debug"], gr.skip(), gr.skip(),
        )
    decision = result["answers"]["route"]
    nimble_choice = decision["choice"]
    correct = scene["best"]

    if nimble_choice == correct:
        game["nimble"] += 1
    if mode == MODE_PREDICT:
        if user_choice == nimble_choice:
            game["player"] += 1
        event = (
            "✅ Your prediction matched Nimble."
            if user_choice == nimble_choice
            else "🔎 Your prediction differed from Nimble."
        )
    elif mode == MODE_DUEL:
        if user_choice == correct:
            game["player"] += 1
        event = f"You chose **{user_choice.title()}**; Nimble chose **{nimble_choice.title()}**."
    else:
        event = f"Nimble chose **{nimble_choice.title()}**."

    game["resolved"] = True
    confidence = decision.get("confidence")
    conf_text = f" · concentration score {confidence:.2f}" if isinstance(confidence, (float, int)) else ""
    yes_prob = result["answers"].get("left_hazard", {}).get("noul")
    yes_text = f"{float(yes_prob) * 100:.1f}%" if isinstance(yes_prob, (int, float)) else "n/a"
    risk = result["answers"].get("left_risk", {}).get("score")
    risk_text = f"{float(risk):.2f} / 2" if isinstance(risk, (int, float)) else "n/a"
    info = (
        scoreboard(game, mode)
        + f"\n\n{event}\n\n**Game answer key:** {direction_label(correct, game.get('language', 'en'))} — {scene['reason']}\n\n"
        + f"**Nimble:** {elapsed_ms:.0f} ms{conf_text} · "
        + f"P(left route hazardous): {yes_text} · Left route risk score: {risk_text}"
        + "\n\n*Probability is not calibrated accuracy; the confidence metric reflects the distribution's concentration, not correctness.*"
    )
    return (
        game,
        scene_markdown(game),
        gr.update(interactive=False),
        info,
        probability_html(decision.get("probabilities", {}), nimble_choice),
        game["debug"],
        gr.update(interactive=False),
        gr.update(interactive=True),
    )


def next_round(game: dict[str, Any], mode: str):
    if not game or not game.get("active"):
        gr.Info("Click Start Game to begin a new game.")
        return (gr.skip(),) * 8
    if not game.get("resolved"):
        gr.Info("Choose a route and click Ask Nimble to finish this round first.")
        return (gr.skip(),) * 8
    mode = game["mode"]
    if game["round"] >= ROUNDS - 1:
        game["active"] = False
        final = (
            f"### 🏁 Game finished\n\n{scoreboard(game, mode)}\n\n"
            + (
                "You've seen how typed choices, boolean probabilities, and rubric scores work. "
                "Press **Start Game** to play another set of scenarios."
            )
        )
        return (
            game, final, gr.update(interactive=False),
            "**Session completed.** You can inspect the last response below.",
            "", game.get("debug", []), gr.update(interactive=False), gr.update(interactive=False),
        )
    game["round"] += 1
    game["resolved"] = False
    scene = current_scene(game)
    hint = "Click *Ask Nimble*." if mode == MODE_WATCH else "Choose a route, then click *Ask Nimble*."
    return (
        game,
        scene_markdown(game),
        gr.update(choices=option_choices(scene), value=None,
                  interactive=(mode != MODE_WATCH)),
        scoreboard(game, mode) + "\n\n" + hint,
        "_Probabilities will appear after a model decision._",
        game.get("debug", []), gr.update(interactive=True), gr.update(interactive=False),
    )
