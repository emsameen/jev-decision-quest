"""Exercise Gradio's session-state flow without a running Ollama server."""

import unittest
from unittest.mock import Mock, patch

from gradio.state_holder import SessionState

import gradio as gr

from decision_quest import config, game as handlers
from decision_quest.ui import create_app
from decision_quest.localization import catalog, direction_label, localized_scene
from decision_quest.ollama import build_payload, call_model
from decision_quest.presentation import decision_breakdown_html, option_choices, scene_markdown
from decision_quest.scenes import SCENES


def model_result(scene, *, debug=None):
    return {
        "answers": {
            "route": {"choice": scene["best"], "probabilities": {scene["best"]: 1}}
        }
    }, 1.0


class GameFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.demo = create_app()
        self.game_state = self.demo.fns[0].outputs[0]

    async def event(self, index, inputs, session):
        return await self.demo.process_api(index, inputs, state=session)

    async def test_full_games_and_repeated_clicks(self):
        for language in ("en", "ar", "de"):
            with self.subTest(language=language), patch.object(
                handlers, "call_model", side_effect=model_result
            ) as model, patch.object(gr, "Info"):
                session = SessionState(self.demo)
                await self.event(1, [None, None], session)
                model.assert_not_called()
                started = await self.event(0, [language], session)
                self.assertFalse(started["data"][7]["interactive"])
                for round_index in range(config.ROUNDS):
                    game = session[self.game_state._id]
                    self.assertEqual(game["round"], round_index)
                    self.assertEqual(game["language"], language)
                    scene = localized_scene(handlers.current_scene(game), language)
                    choice = scene["best"]
                    enabled = await self.event(3, [choice], session)
                    self.assertTrue(enabled["data"][0]["interactive"])
                    result = await self.event(1, [None, choice], session)
                    self.assertTrue(session[self.game_state._id]["resolved"])
                    self.assertEqual(session[self.game_state._id]["model"], round_index + 1)
                    self.assertEqual(session[self.game_state._id]["player"], round_index + 1)
                    self.assertEqual(session[self.game_state._id]["matches"], round_index + 1)
                    self.assertIn(
                        f"You chose **{direction_label(choice, language)}**",
                        result["data"][5],
                    )
                    self.assertIn("Fixed-rule answer", result["data"][5])
                    reasoning = session[self.game_state._id]["debug"][-1]["reasoning"]
                    self.assertEqual(reasoning["correct_route"], scene["best"])
                    self.assertEqual(reasoning["explanation"], scene["reason"])
                    self.assertEqual(reasoning["source"], "fixed game rules")
                    await self.event(1, [None, choice], session)
                    self.assertEqual(model.call_count, round_index + 1)
                    await self.event(2, [None], session)
                    # A duplicate Next click must not skip an unresolved round.
                    await self.event(2, [None], session)
                self.assertEqual(len(session[self.game_state._id]["debug"]), config.ROUNDS)
                self.assertFalse(session[self.game_state._id]["active"])
                await self.event(1, [None, choice], session)
                self.assertEqual(model.call_count, config.ROUNDS)
                await self.event(0, [language], session)
                self.assertEqual(session[self.game_state._id]["debug"], [])
                self.assertEqual(session[self.game_state._id]["model"], 0)
                self.assertFalse(session[self.game_state._id]["resolved"])

    async def test_model_failure_leaves_round_retryable(self):
        session = SessionState(self.demo)
        await self.event(0, ["en"], session)
        choice = handlers.current_scene(session[self.game_state._id])["best"]
        with patch.object(handlers, "call_model", side_effect=gr.Error("Offline")):
            result = await self.event(1, [None, choice], session)
            self.assertIn("Offline", result["data"][3])
            self.assertIn("Offline", session[self.game_state._id]["debug"][0]["error"])
            self.assertIn("reasoning", session[self.game_state._id]["debug"][0])
        self.assertFalse(session[self.game_state._id]["resolved"])
        self.assertEqual(session[self.game_state._id]["model"], 0)
        with patch.object(handlers, "call_model", side_effect=model_result):
                await self.event(1, [None, choice], session)
        self.assertTrue(session[self.game_state._id]["resolved"])

    async def test_asking_without_a_route_is_ignored(self):
        session = SessionState(self.demo)
        await self.event(0, ["en"], session)
        with patch.object(gr, "Info") as info, patch.object(
            handlers, "call_model"
        ) as model:
            await self.event(1, [None, None], session)
        info.assert_called_once()
        model.assert_not_called()
        self.assertEqual(session[self.game_state._id]["debug"], [])


class DebugTests(unittest.TestCase):
    def test_records_actual_request_and_response(self):
        result, _ = model_result(SCENES[0])
        response = Mock(status_code=200, text="response text")
        response.json.return_value = result
        record = {}
        with patch("decision_quest.ollama.requests.post", return_value=response) as post:
            actual, _ = call_model(SCENES[0], debug=record)
        self.assertEqual(actual, result)
        self.assertEqual(record["request"]["json"], post.call_args.kwargs["json"])
        self.assertEqual(record["request"]["url"], post.call_args.args[0])
        self.assertEqual(record["response"], result)
        self.assertEqual(record["status_code"], 200)
        self.assertIsNone(record["error"])
        self.assertGreaterEqual(record["elapsed_ms"], 0)

    def test_records_http_failure_body(self):
        import requests
        response = Mock(status_code=500, text="Model failed")
        response.json.side_effect = ValueError("Not JSON")
        response.raise_for_status.side_effect = requests.exceptions.HTTPError("Failed")
        record = {}
        with patch("decision_quest.ollama.requests.post", return_value=response):
            with self.assertRaises(gr.Error):
                call_model(SCENES[0], debug=record)
        self.assertEqual(record["response"], "Model failed")
        self.assertEqual(record["status_code"], 500)
        self.assertIn("500", record["error"])

    def test_decision_breakdown_shows_all_three_question_types(self):
        answers = {
            "route": {
                "type": "choice",
                "choice": "middle",
                "probabilities": {"left": 0.1, "middle": 0.8, "right": 0.1},
                "confidence": 0.5,
            },
            "left_hazard": {"type": "noul", "noul": 0.25},
            "left_risk": {
                "type": "score",
                "score": 0.7,
                "legend": {"0": "Low risk", "1": "Medium risk", "2": "High risk"},
                "probabilities": {"0": 0.5, "1": 0.3, "2": 0.2},
            },
        }
        rendered = decision_breakdown_html(answers, "middle")
        for label in ("choice", "noul", "score", "Low risk", "Medium risk", "High risk"):
            with self.subTest(label=label):
                self.assertIn(label, rendered)
        self.assertIn("80.0%", rendered)
        self.assertIn("25.0%", rendered)
        self.assertIn("Expected score: <strong>0.70 / 2</strong>", rendered)


class LocalizationTests(unittest.TestCase):
    def test_arabic_catalog_and_payload(self):
        translations = catalog("ar")
        self.assertEqual(set(translations["scenes"]), {s["id"] for s in SCENES})
        for original in SCENES:
            with self.subTest(scene=original["id"]):
                translated = localized_scene(original, "ar")
                self.assertEqual(translated["best"], original["best"])
                for key in ("title", "goal", "story", "reason"):
                    self.assertNotEqual(translated[key], original[key])
                self.assertEqual(set(translated["paths"]), set(config.DIRECTIONS))
                self.assertEqual([v for _, v in option_choices(translated)],
                                 list(config.DIRECTIONS))
                payload = build_payload(translated)
                self.assertEqual(payload["state"]["goal"], translated["goal"])
                self.assertEqual(payload["questions"]["route"]["criteria"], translated["paths"])
                self.assertEqual(payload["questions"]["route"]["instructions"],
                                 translations["questions"]["route"])
                self.assertEqual(payload["questions"]["left_risk"]["criteria"],
                                 translations["questions"]["risk_criteria"])
        game = {"round": 0, "order": [0], "language": "ar"}
        self.assertIn('dir="rtl"', scene_markdown(game))
        self.assertIn("Round 1", scene_markdown(game))

    def test_german_catalog_and_payload(self):
        translations = catalog("de")
        self.assertEqual(set(translations["scenes"]), {s["id"] for s in SCENES})
        for original in SCENES:
            with self.subTest(scene=original["id"]):
                scene = localized_scene(original, "de")
                self.assertEqual(scene["best"], original["best"])
                for key in ("title", "goal", "story", "reason"):
                    self.assertNotEqual(scene[key], original[key])
                self.assertEqual(set(scene["paths"]), set(config.DIRECTIONS))
                for direction in config.DIRECTIONS:
                    self.assertNotEqual(scene["paths"][direction], original["paths"][direction])
                payload = build_payload(scene)
                self.assertEqual(payload["state"]["paths"], scene["paths"])
                for key in ("route", "left_hazard", "left_risk"):
                    self.assertEqual(payload["questions"][key]["instructions"],
                                     translations["questions"][key])
                self.assertEqual(payload["questions"]["left_risk"]["criteria"],
                                 translations["questions"]["risk_criteria"])
                self.assertEqual([v for _, v in option_choices(scene)], list(config.DIRECTIONS))
                self.assertTrue(option_choices(scene)[0][0].startswith("Links —"))
        rendered = scene_markdown({"round": 0, "order": [0], "language": "de"})
        self.assertIn("**Links**", rendered)
        self.assertNotIn('dir="rtl"', rendered)
        self.assertIn("Round 1", rendered)

    def test_partial_catalog_falls_back_without_mutating_english(self):
        english = catalog("en")
        partial = {
            "directions": {"left": "Links"},
            "questions": {"route": "Translated question"},
            "scenes": {"flooded_valley": {"paths": {"left": "Translated path"}}},
        }
        catalog.cache_clear()
        try:
            with patch("decision_quest.localization._read_catalog",
                       side_effect=lambda code: english if code == "en" else partial):
                scene = localized_scene({"id": "flooded_valley", "best": "middle"}, "de")
                self.assertEqual(scene["paths"]["left"], "Translated path")
                self.assertEqual(scene["paths"]["right"], english["scenes"]["flooded_valley"]["paths"]["right"])
                self.assertEqual(scene["goal"], english["scenes"]["flooded_valley"]["goal"])
                payload = build_payload(scene)
                self.assertEqual(payload["questions"]["route"]["instructions"], "Translated question")
                self.assertEqual(payload["questions"]["left_hazard"]["instructions"], english["questions"]["left_hazard"])
                self.assertEqual(catalog("de")["directions"]["middle"], "Middle")
                self.assertEqual(catalog("de")["scenes"]["space_station"], english["scenes"]["space_station"])
                self.assertEqual(catalog("en"), english)
        finally:
            catalog.cache_clear()

    def test_english_catalog_is_complete(self):
        english = catalog("en")
        self.assertEqual(set(english["scenes"]), {s["id"] for s in SCENES})
        self.assertEqual(set(english["directions"]), set(config.DIRECTIONS))
        for original in SCENES:
            scene = localized_scene(original, "en")
            self.assertEqual(scene["goal"], english["scenes"][scene["id"]]["goal"])
            self.assertEqual(build_payload(scene)["questions"]["route"]["instructions"], english["questions"]["route"])

    def test_english_fallback(self):
        for language in ("en", "unknown"):
            scene = localized_scene(SCENES[0], language)
            self.assertEqual(scene["goal"], SCENES[0]["goal"])
            self.assertEqual(scene["language"], "en")
            self.assertIn("Which one", build_payload(scene)["questions"]["route"]["instructions"])


if __name__ == "__main__":
    unittest.main()
