"""Markdown and HTML formatting for the game interface."""

import html
from typing import Any

from .config import DIRECTIONS, MODE_PREDICT, ROUNDS
from .scenes import current_scene
from .localization import direction_label


def scene_markdown(game: dict[str, Any]) -> str:
    scene = current_scene(game)
    if scene["language"] == "ar":
        paths = "".join(
            f"<li><b>{direction_label(d, 'ar')}</b>: {html.escape(scene['paths'][d])}</li>"
            for d in DIRECTIONS
        )
        return (
            f"### Round {game['round'] + 1} / {ROUNDS}\n\n"
            f'<div lang="ar" dir="rtl">'
            f"<h3>{html.escape(scene['title'])}</h3>"
            f"<p>{html.escape(scene['goal'])}</p>"
            f"<p>{html.escape(scene['story'])}</p><ul>{paths}</ul></div>"
        )
    paths = "\n".join(
        f"- **{direction_label(direction, scene['language'])}**: {scene['paths'][direction]}" for direction in DIRECTIONS
    )
    return (
        f"### Round {game['round'] + 1} / {ROUNDS} · {scene['title']}\n\n"
        f"**Mission:** {scene['goal']}\n\n"
        f"{scene['story']}\n\n{paths}"
    )


def scoreboard(game: dict[str, Any], mode: str) -> str:
    label = "Matching predictions" if mode == MODE_PREDICT else "Your safe routes"
    return (
        f"**{label}: {game['player']}** &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"**Nimble safe routes: {game['nimble']}**"
    )


def option_choices(scene: dict[str, Any]) -> list[tuple[str, str]]:
    language = scene.get("language", "en")
    choices = []
    for d in DIRECTIONS:
        label = f"{direction_label(d, language)} — {scene['paths'][d]}"
        if language == "ar":
            label = "\u2067" + label + "\u2069"  # Isolate RTL text within the English UI.
        choices.append((label, d))
    return choices


def probability_html(probs: dict[str, float], selected: str) -> str:
    rows = []
    for d in DIRECTIONS:
        p = max(0.0, min(1.0, float(probs.get(d, 0))))
        color = "#0f766e" if d == selected else "#64748b"
        rows.append(
            f'<div style="margin:11px 0">'
            f'<div style="display:flex;justify-content:space-between;font-size:14px">'
            f'<b>{html.escape(d.title())}</b><span>{p * 100:.1f}%</span></div>'
            f'<div style="height:13px;background:#e2e8f0;border-radius:12px;overflow:hidden">'
            f'<div style="width:{p * 100:.2f}%;height:100%;background:{color};border-radius:12px">'
            f'</div></div></div>'
        )
    return "<div style='padding:8px 4px'>" + "".join(rows) + "</div>"
