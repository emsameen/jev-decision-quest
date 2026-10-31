"""Exercise Gradio's session-state flow without a running Ollama server."""

import unittest
from itertools import product
from unittest.mock import Mock, patch

from gradio.state_holder import SessionState

import gradio as gr

from decision_quest import config, game as handlers
from decision_quest.ui import create_app
from decision_quest.localization import catalog, localized_scene
from decision_quest.ollama import build_payload, call_nimble
from decision_quest.presentation import option_choices, scene_markdown
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
        for mode, language in product(
            (config.MODE_PREDICT, config.MODE_DUEL, config.MODE_WATCH), ("en", "ar", "de")
        ):
            with self.subTest(mode=mode, language=language), patch.object(
                handlers, "call_nimble", side_effect=model_result
            ) as model, patch.object(gr, "Info"):
                session = SessionState(self.demo)
                await self.event(1, [None, mode, None], session)
                model.assert_not_called()
                await self.event(0, [mode, language], session)
                for round_index in range(config.ROUNDS):
                    game = session[self.game_state._id]
                    self.assertEqual(game["round"], round_index)
                    self.assertEqual(game["language"], language)
                    choice = handlers.current_scene(game)["best"]
                    await self.event(1, [None, mode, choice], session)
                    self.assertTrue(session[self.game_state._id]["resolved"])
                    self.assertEqual(session[self.game_state._id]["nimble"], round_index + 1)
                    await self.event(1, [None, mode, choice], session)
                    self.assertEqual(model.call_count, round_index + 1)
                    await self.event(2, [None, mode], session)
                    # A duplicate Next click must not skip an unresolved round.
                    await self.event(2, [None, mode], session)
                self.assertEqual(len(session[self.game_state._id]["debug"]), config.ROUNDS)
                self.assertFalse(session[self.game_state._id]["active"])
                await self.event(1, [None, mode, choice], session)
                self.assertEqual(model.call_count, config.ROUNDS)
                await self.event(0, [mode, language], session)
                self.assertEqual(session[self.game_state._id]["debug"], [])
                self.assertEqual(session[self.game_state._id]["nimble"], 0)
                self.assertFalse(session[self.game_state._id]["resolved"])

    async def test_model_failure_leaves_round_retryable(self):
        session = SessionState(self.demo)
        await self.event(0, [config.MODE_WATCH, "en"], session)
        with patch.object(handlers, "call_nimble", side_effect=gr.Error("Offline")):
            result = await self.event(1, [None, config.MODE_WATCH, None], session)
            self.assertIn("Offline", result["data"][3])
            self.assertIn("Offline", session[self.game_state._id]["debug"][0]["error"])
        self.assertFalse(session[self.game_state._id]["resolved"])
        self.assertEqual(session[self.game_state._id]["nimble"], 0)
        with patch.object(handlers, "call_nimble", side_effect=model_result):
            await self.event(1, [None, config.MODE_WATCH, None], session)
        self.assertTrue(session[self.game_state._id]["resolved"])


class DebugTests(unittest.TestCase):
    def test_records_actual_request_and_response(self):
        result, _ = model_result(SCENES[0])
        response = Mock(status_code=200, text="response text")
        response.json.return_value = result
        record = {}
        with patch("decision_quest.ollama.requests.post", return_value=response) as post:
            actual, _ = call_nimble(SCENES[0], debug=record)
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
                call_nimble(SCENES[0], debug=record)
        self.assertEqual(record["response"], "Model failed")
        self.assertEqual(record["status_code"], 500)
        self.assertIn("500", record["error"])


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
