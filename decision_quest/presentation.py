"""Markdown and HTML formatting for the game interface."""

import html
import math
from typing import Any

from .config import DIRECTIONS
from .models import GameSession, Scenario
from .scenes import SceneRepository


class GamePresenter:
    """Render game state without owning or mutating a player's session."""

    def __init__(self, scenes: SceneRepository):
        self.scenes = scenes
        self.localization = scenes.localization

    def scene_markdown(self, game: GameSession) -> str:
        scene = self.scenes.current(game)
        completed = game.completed_rounds
        progress = (
            f'<div class="quest-progress"><span>Adventure progress · {completed} / {game.total_rounds} complete</span>'
            f'<progress value="{completed}" max="{game.total_rounds}" aria-label="Completed rounds"></progress></div>\n\n'
        )
        if scene.language == "ar":
            paths = "".join(
                f"<li><b>{self.localization.direction_label(d, 'ar')}</b>: {html.escape(scene.paths[d])}</li>"
                for d in DIRECTIONS
            )
            return (
                progress + f"### Round {game.round + 1} / {game.total_rounds}\n\n"
                f'<div lang="ar" dir="rtl">'
                f"<h3>{html.escape(scene.title)}</h3>"
                f"<p>{html.escape(scene.goal)}</p>"
                f"<p>{html.escape(scene.story)}</p><ul>{paths}</ul></div>"
            )
        paths = "\n".join(
            f"- **{self.localization.direction_label(direction, scene.language)}**: {scene.paths[direction]}" for direction in DIRECTIONS
        )
        return (
            progress + f"### Round {game.round + 1} / {game.total_rounds} · {scene.title}\n\n"
            f"**Mission:** {scene.goal}\n\n"
            f"{scene.story}\n\n{paths}"
        )

    @staticmethod
    def scoreboard(game: GameSession) -> str:
        return (
            f"**Safe routes:** You {game.player} · Model {game.model}"
            f"&nbsp;&nbsp;|&nbsp;&nbsp; **Matches:** {game.matches}"
        )

    @staticmethod
    def debug_summary_markdown(records: list[dict[str, Any]]) -> str:
        if not records:
            return "_Round summaries will appear after you run the model._"

        summaries = []
        for record in records:
            reasoning = record.get("reasoning", {})
            response = record.get("response")
            answers = response.get("answers", {}) if isinstance(response, dict) else {}
            route = answers.get("route", {})
            probabilities = route.get("probabilities", {})
            choice = route.get("choice")
            selected_probability = probabilities.get(choice) if isinstance(probabilities, dict) else None
            player_choice = record.get("player_choice_label")
            details = [f"You chose **{player_choice}**"] if player_choice else []
            if choice:
                details.append(f"Model chose **{choice.title()}**")
                if isinstance(selected_probability, (int, float)):
                    details.append(f"route weight {selected_probability * 100:.1f}%")
                matched = record.get("matched_model")
                if isinstance(matched, bool):
                    details.append("your choices matched" if matched else "your choices differed")
            else:
                details.append("Model decision unavailable")

            hazard = answers.get("left_hazard", {}).get("noul")
            if isinstance(hazard, (int, float)):
                details.append(f"left-route hazard {hazard * 100:.1f}%")
            risk = answers.get("left_risk", {}).get("score")
            if isinstance(risk, (int, float)):
                details.append(f"left-route risk {risk:.2f}/2")

            status = record.get("status_code")
            elapsed = record.get("elapsed_ms")
            trace = []
            if status is not None:
                trace.append(f"HTTP {status}")
            if isinstance(elapsed, (int, float)):
                trace.append(f"{elapsed:.0f} ms")
            if record.get("error"):
                trace.append(f"Error: {record['error']}")
            if not trace:
                trace.append("Request pending")

            answer = reasoning.get("correct_route_label", reasoning.get("correct_route", "unknown"))
            explanation = reasoning.get("explanation", "")
            summaries.append(
                f"#### Round {record.get('round', '?')}\n\n"
                f"**Comparison:** {' · '.join(details)}  \n"
                f"**Fixed-rule answer:** `{answer}` — {explanation}  \n"
                f"**Request:** {' · '.join(trace)}"
            )
        return "\n\n---\n\n".join(summaries)

    def option_choices(self, scene: Scenario) -> list[tuple[str, str]]:
        language = scene.language
        choices = []
        for d in DIRECTIONS:
            label = f"{self.localization.direction_label(d, language)} — {scene.paths[d]}"
            if language == "ar":
                label = "\u2067" + label + "\u2069"  # Isolate RTL text within the English UI.
            choices.append((label, d))
        return choices

    @staticmethod
    def _number(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    def _probability_row(self, label: str, probability: Any, color: str) -> str:
        value = self._number(probability)
        if value is None:
            percent_text = "—"
            width = 0
        else:
            value = max(0.0, min(1.0, value))
            percent_text = f"{value * 100:.1f}%"
            width = value * 100
        return (
            '<div style="display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 12px;'
            'align-items:center;margin:9px 0">'
            f'<span>{html.escape(label)}</span><strong>{percent_text}</strong>'
            '<div style="grid-column:1/-1;height:8px;background:#173e4b;border-radius:8px;overflow:hidden">'
            f'<div style="width:{width:.2f}%;height:100%;background:{color}"></div>'
            '</div></div>'
        )

    def decision_breakdown_html(
        self, answers: dict[str, Any], selected: str, language: str = "en"
    ) -> str:
        route = answers.get("route", {})
        route_probabilities = route.get("probabilities", {})
        route_rows = []
        for d in DIRECTIONS:
            color = "#54dfbc" if d == selected else "#5ac6e2"
            route_rows.append(
                self._probability_row(
                    self.localization.direction_label(d, language), route_probabilities.get(d), color
                )
            )
        selected_label = html.escape(self.localization.direction_label(selected, language))
        route_confidence = self._number(route.get("confidence"))
        concentration = (
            f" · concentration {route_confidence:.2f}" if route_confidence is not None else ""
        )
        route_section = (
            '<section style="padding:12px 0;border-bottom:1px solid #285361">'
            '<h4 style="margin:0 0 4px">choice · Route selection</h4>'
            f'<p style="margin:0 0 8px;color:#b8d3db">Selected: <strong>{selected_label}</strong>'
            f'{concentration}</p>{"".join(route_rows)}</section>'
        )

        hazard = answers.get("left_hazard", {})
        hazard_probability = self._number(hazard.get("noul"))
        if hazard_probability is None:
            hazard_section = (
                '<section style="padding:12px 0;border-bottom:1px solid #285361">'
                '<h4 style="margin:0 0 4px">noul · Hazard check</h4>'
                '<p style="margin:0;color:#b8d3db">No hazard estimate returned.</p></section>'
            )
        else:
            hazard_probability = max(0.0, min(1.0, hazard_probability))
            hazard_section = (
                '<section style="padding:12px 0;border-bottom:1px solid #285361">'
                '<h4 style="margin:0 0 4px">noul · Left-route hazard</h4>'
                '<p style="margin:0 0 8px;color:#b8d3db">Probability that the description states a hazard</p>'
                f'{self._probability_row("Yes", hazard_probability, "#ff827d")}'
                f'{self._probability_row("No", 1 - hazard_probability, "#54dfbc")}'
                '</section>'
            )

        risk = answers.get("left_risk", {})
        risk_probabilities = risk.get("probabilities", {})
        legend = risk.get("legend", {})
        risk_rows = []
        for level in range(3):
            label = legend.get(str(level), legend.get(level, f"Level {level}"))
            probability = risk_probabilities.get(str(level), risk_probabilities.get(level))
            risk_rows.append(self._probability_row(f"{level} · {label}", probability, "#ffb74d"))
        expected_score = self._number(risk.get("score"))
        score_text = f"{expected_score:.2f} / 2" if expected_score is not None else "Not returned"
        risk_section = (
            '<section style="padding:12px 0">'
            '<h4 style="margin:0 0 4px">score · Left-route risk rubric</h4>'
            f'<p style="margin:0 0 8px;color:#b8d3db">Expected score: <strong>{score_text}</strong></p>'
            f'{"".join(risk_rows)}</section>'
        )
        return (
            '<div style="padding:4px 2px">'
            f'{route_section}{hazard_section}{risk_section}'
            '<p style="margin:8px 0 0;color:#a1c0cb;font-size:12px">'
            'Probabilities are model estimates, not calibrated accuracy.</p></div>'
        )
