"""Scenario rules and their localized content."""

from .localization import LocalizationCatalog
from .models import GameSession, Scenario, SceneRule

# Correct routes belong to game rules, never to translations or model output.
SCENE_RULES = (
    SceneRule("flooded_valley", "middle"),
    SceneRule("space_station", "middle"),
    SceneRule("forest_evacuation", "right"),
    SceneRule("clockwork_castle", "left"),
    SceneRule("mountain_descent", "middle"),
    SceneRule("jungle_crossing", "left"),
    SceneRule("robot_workshop", "right"),
    SceneRule("volcano_base", "left"),
)


class SceneRepository:
    """Resolve session positions into scenarios using one question catalog."""

    def __init__(self, localization: LocalizationCatalog | None = None):
        self.localization = localization if localization is not None else LocalizationCatalog()

    def __len__(self) -> int:
        return len(SCENE_RULES)

    def get(self, index: int, language: str = "en") -> Scenario:
        return self.localization.localize(SCENE_RULES[index], language)

    def current(self, game: GameSession) -> Scenario:
        return self.get(game.order[game.round], game.language)
