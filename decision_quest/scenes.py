"""Scenario identifiers and fixed answer keys, independent of translations."""

from typing import Any

from .localization import localized_scene

# Correct routes belong to game rules, never to translations or model output.
SCENE_RULES = [
    {'id': 'flooded_valley', 'best': 'middle'},
    {'id': 'space_station', 'best': 'middle'},
    {'id': 'forest_evacuation', 'best': 'right'},
    {'id': 'clockwork_castle', 'best': 'left'},
    {'id': 'mountain_descent', 'best': 'middle'},
    {'id': 'jungle_crossing', 'best': 'left'},
    {'id': 'robot_workshop', 'best': 'right'},
    {'id': 'volcano_base', 'best': 'left'},
]

# Keep English scenarios available to callers; their text comes from en.json.
SCENES = [localized_scene(rule, "en") for rule in SCENE_RULES]


def current_scene(game: dict[str, Any]) -> dict[str, Any]:
    return localized_scene(
        SCENE_RULES[game["order"][game["round"]]], game.get("language", "en")
    )
