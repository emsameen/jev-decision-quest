"""Exercise the domain classes and Gradio sessions without running Ollama."""

import os
import unittest
from unittest.mock import Mock, patch

import gradio as gr
import requests
from gradio.state_holder import SessionState

from decision_quest.config import AppSettings, DIRECTIONS, ROUNDS
from decision_quest.localization import LocalizationCatalog
from decision_quest.models import GameSession, SceneRule
from decision_quest.ollama import ModelError, OllamaClient
from decision_quest.presentation import GamePresenter
from decision_quest.scenes import SCENE_RULES, SceneRepository
from decision_quest.ui import DecisionQuestApp


def model_result(scene, *, debug=None):
    result = {
        "answers": {
            "route": {"choice": scene.best, "probabilities": {scene.best: 1}}
        }
    }
    if debug is not None:
        debug.update(response=result, status_code=200, elapsed_ms=1.0, error=None)
    return result, 1.0


class GameFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = Mock(spec=OllamaClient)
        self.client.decide.side_effect = model_result
        self.app = DecisionQuestApp(AppSettings(), client=self.client)
        self.demo = self.app.build()
        self.game_state = self.demo.fns[0].outputs[0]

    async def event(self, index, inputs, session):
        return await self.demo.process_api(index, inputs, state=session)

    def state(self, session):
        return session[self.game_state._id]

    async def test_full_games_and_repeated_clicks(self):
        for language in ("en", "ar", "de"):
            with self.subTest(language=language), patch.object(gr, "Info"):
                self.client.reset_mock()
                session = SessionState(self.demo)
                await self.event(1, [None, None], session)
                self.client.decide.assert_not_called()
                started = await self.event(0, [language], session)
                self.assertFalse(started["data"][7]["interactive"])
                for round_index in range(ROUNDS):
                    game = self.state(session)
                    self.assertIsInstance(game, GameSession)
                    self.assertEqual(game.round, round_index)
                    self.assertEqual(game.language, language)
                    scene = self.app.scenes.current(game)
                    choice = scene.best
                    enabled = await self.event(3, [choice], session)
                    self.assertTrue(enabled["data"][0]["interactive"])
                    result = await self.event(1, [None, choice], session)
                    self.assertTrue(self.state(session).resolved)
                    self.assertEqual(game.model, round_index + 1)
                    self.assertEqual(game.player, round_index + 1)
                    self.assertEqual(game.matches, round_index + 1)
                    self.assertIn(
                        f"You chose **{self.app.localization.direction_label(choice, language)}**",
                        result["data"][5],
                    )
                    self.assertIn("Fixed-rule answer", result["data"][5])
                    reasoning = game.debug[-1]["reasoning"]
                    self.assertEqual(reasoning["correct_route"], scene.best)
                    self.assertEqual(reasoning["explanation"], scene.reason)
                    self.assertEqual(reasoning["source"], "fixed game rules")
                    await self.event(1, [None, choice], session)
                    self.assertEqual(self.client.decide.call_count, round_index + 1)
                    await self.event(2, [None], session)
                    # A duplicate Next click must not skip an unresolved round.
                    await self.event(2, [None], session)
                self.assertEqual(len(game.debug), ROUNDS)
                self.assertFalse(game.active)
                await self.event(1, [None, choice], session)
                self.assertEqual(self.client.decide.call_count, ROUNDS)
                await self.event(0, [language], session)
                self.assertEqual(self.state(session).debug, [])
                self.assertEqual(self.state(session).model, 0)
                self.assertFalse(self.state(session).resolved)

    async def test_model_failure_leaves_round_retryable(self):
        session = SessionState(self.demo)
        await self.event(0, ["en"], session)
        game = self.state(session)
        choice = self.app.scenes.current(game).best
        self.client.decide.side_effect = ModelError("Offline")
        result = await self.event(1, [None, choice], session)
        self.assertIn("Offline", result["data"][3])
        self.assertIn("Offline", game.debug[0]["error"])
        self.assertIn("reasoning", game.debug[0])
        self.assertFalse(game.resolved)
        self.assertEqual(game.model, 0)
        self.client.decide.side_effect = model_result
        await self.event(1, [None, choice], session)
        self.assertTrue(game.resolved)
        self.assertEqual(game.player, 1)
        self.assertEqual(len(game.debug), 2)

    async def test_asking_without_a_route_is_ignored(self):
        session = SessionState(self.demo)
        await self.event(0, ["en"], session)
        with patch.object(gr, "Info") as info:
            await self.event(1, [None, None], session)
        info.assert_called_once()
        self.client.decide.assert_not_called()
        self.assertEqual(self.state(session).debug, [])

    async def test_browser_sessions_keep_independent_scores_history_and_language(self):
        english, arabic = SessionState(self.demo), SessionState(self.demo)
        self.assertIsNot(self.state(english), self.state(arabic))
        await self.event(0, ["en"], english)
        await self.event(0, ["ar"], arabic)
        first, second = self.state(english), self.state(arabic)
        await self.event(1, [None, self.app.scenes.current(first).best], english)
        self.assertEqual((first.player, len(first.debug), first.language), (1, 1, "en"))
        self.assertEqual((second.player, second.debug, second.language), (0, [], "ar"))
        self.assertFalse(second.resolved)
        await self.event(0, ["de"], arabic)
        self.assertEqual(self.state(arabic).language, "de")
        self.assertTrue(first.resolved)
        self.assertEqual((first.player, len(first.debug)), (1, 1))

    async def test_debug_visibility_toggle(self):
        session = SessionState(self.demo)
        shown = await self.event(4, [True], session)
        hidden = await self.event(4, [False], session)
        self.assertTrue(shown["data"][0]["visible"])
        self.assertFalse(hidden["data"][0]["visible"])


class SessionRuleTests(unittest.TestCase):
    def test_scores_safe_routes_and_agreement_independently(self):
        for player, model, correct, expected in (
            ("left", "left", "right", (0, 0, 1)),
            ("left", "right", "left", (1, 0, 0)),
            ("left", "right", "right", (0, 1, 0)),
            ("right", "right", "right", (1, 1, 1)),
        ):
            with self.subTest(player=player, model=model, correct=correct):
                session = GameSession.start([0])
                session.score_round(player, model, correct)
                self.assertEqual((session.player, session.model, session.matches), expected)
                self.assertEqual(session.completed_rounds, 1)
                with self.assertRaises(ValueError):
                    session.score_round(player, model, correct)
                self.assertEqual((session.player, session.model, session.matches), expected)
                session.advance()
                self.assertFalse(session.active)

    def test_cannot_advance_or_score_an_inactive_or_unresolved_game(self):
        session = GameSession()
        with self.assertRaises(ValueError):
            session.score_round("left", "left", "left")
        session = GameSession.start([0, 1])
        with self.assertRaises(ValueError):
            session.advance()
        with self.assertRaises(ValueError):
            session.score_round("invalid", "left", "left")
        self.assertEqual((session.player, session.model, session.matches), (0, 0, 0))
        self.assertFalse(session.resolved)
        session.score_round("left", "left", "left")
        session.advance()
        self.assertEqual(session.round, 1)
        self.assertFalse(session.resolved)

    def test_start_copies_order_and_rejects_empty_or_duplicate_scenarios(self):
        order = [0, 1]
        session = GameSession.start(order)
        order.clear()
        self.assertEqual(session.total_rounds, 2)
        for invalid in ([], [0, 0]):
            with self.subTest(order=invalid), self.assertRaises(ValueError):
                GameSession.start(invalid)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.scenes = SceneRepository()
        self.client = OllamaClient(AppSettings(), self.scenes.localization)
        self.scene = self.scenes.get(0)

    def test_records_actual_request_and_response(self):
        result, _ = model_result(self.scene)
        response = Mock(status_code=200, text="response text")
        response.json.return_value = result
        record = {}
        with patch("decision_quest.ollama.requests.post", return_value=response) as post:
            actual, _ = self.client.decide(self.scene, debug=record)
        self.assertEqual(actual, result)
        self.assertEqual(record["request"]["json"], post.call_args.kwargs["json"])
        self.assertEqual(record["request"]["url"], post.call_args.args[0])
        self.assertEqual(record["response"], result)
        self.assertEqual(record["status_code"], 200)
        self.assertIsNone(record["error"])
        self.assertGreaterEqual(record["elapsed_ms"], 0)

    def test_records_http_failure_body(self):
        response = Mock(status_code=500, text="Model failed")
        response.json.side_effect = ValueError("Not JSON")
        response.raise_for_status.side_effect = requests.exceptions.HTTPError("Failed")
        record = {}
        with patch("decision_quest.ollama.requests.post", return_value=response):
            with self.assertRaises(ModelError):
                self.client.decide(self.scene, debug=record)
        self.assertEqual(record["response"], "Model failed")
        self.assertEqual(record["status_code"], 500)
        self.assertIn("500", record["error"])

    def test_connection_and_timeout_failures_are_recorded(self):
        for failure, message in (
            (requests.exceptions.ConnectionError("Offline"), "Cannot reach Ollama"),
            (requests.exceptions.Timeout("Slow"), "OLLAMA_TIMEOUT"),
        ):
            with self.subTest(error=type(failure).__name__):
                record = {}
                with patch("decision_quest.ollama.requests.post", side_effect=failure):
                    with self.assertRaisesRegex(ModelError, message):
                        self.client.decide(self.scene, debug=record)
                self.assertIn(message, record["error"])
                self.assertIsNone(record["status_code"])
                self.assertGreaterEqual(record["elapsed_ms"], 0)

    def test_invalid_decisions_are_rejected_before_scoring(self):
        for result in ({}, {"answers": None}, {"answers": {"route": {"choice": "invalid"}}}):
            with self.subTest(result=result):
                response = Mock(status_code=200, text="invalid result")
                response.json.return_value = result
                record = {}
                with patch("decision_quest.ollama.requests.post", return_value=response):
                    with self.assertRaises(ModelError):
                        self.client.decide(self.scene, debug=record)
                self.assertEqual(record["response"], result)
                self.assertIn("Unexpected model response", record["error"])

    def test_client_instances_use_their_own_model_endpoint_and_timeout(self):
        clients = (
            OllamaClient(AppSettings(ollama_url="http://first:11434/", model="first", timeout=10)),
            OllamaClient(AppSettings(ollama_url="http://second:11434", model="second", timeout=20)),
        )
        response = Mock(status_code=200, text="response text")
        response.json.return_value = model_result(self.scene)[0]
        for client in clients:
            with self.subTest(model=client.settings.model):
                with patch("decision_quest.ollama.requests.post", return_value=response) as post:
                    client.decide(self.scene)
                self.assertEqual(post.call_args.args[0], client.settings.endpoint)
                self.assertEqual(post.call_args.kwargs["json"]["model"], client.settings.model)
                self.assertEqual(post.call_args.kwargs["timeout"], (10, client.settings.timeout))


class PresentationTests(unittest.TestCase):
    def test_decision_breakdown_shows_all_three_question_types(self):
        answers = {
            "route": {
                "type": "choice", "choice": "middle",
                "probabilities": {"left": 0.1, "middle": 0.8, "right": 0.1}, "confidence": 0.5,
            },
            "left_hazard": {"type": "noul", "noul": 0.25},
            "left_risk": {
                "type": "score", "score": 0.7,
                "legend": {"0": "Low risk", "1": "Medium risk", "2": "High risk"},
                "probabilities": {"0": 0.5, "1": 0.3, "2": 0.2},
            },
        }
        rendered = GamePresenter(SceneRepository()).decision_breakdown_html(answers, "middle")
        for label in ("choice", "noul", "score", "Low risk", "Medium risk", "High risk"):
            with self.subTest(label=label):
                self.assertIn(label, rendered)
        self.assertIn("80.0%", rendered)
        self.assertIn("25.0%", rendered)
        self.assertIn("Expected score: <strong>0.70 / 2</strong>", rendered)


class LocalizationTests(unittest.TestCase):
    def setUp(self):
        self.localization = LocalizationCatalog()
        self.scenes = SceneRepository(self.localization)
        self.client = OllamaClient(AppSettings(), self.localization)
        self.presenter = GamePresenter(self.scenes)

    def test_arabic_catalog_and_payload(self):
        translations = self.localization.catalog("ar")
        self.assertEqual(set(translations["scenes"]), {rule.id for rule in SCENE_RULES})
        for index in range(len(self.scenes)):
            original, translated = self.scenes.get(index), self.scenes.get(index, "ar")
            with self.subTest(scene=original.id):
                self.assertEqual(translated.best, original.best)
                for key in ("title", "goal", "story", "reason"):
                    self.assertNotEqual(getattr(translated, key), getattr(original, key))
                self.assertEqual(set(translated.paths), set(DIRECTIONS))
                self.assertEqual([v for _, v in self.presenter.option_choices(translated)], list(DIRECTIONS))
                payload = self.client.build_payload(translated)
                self.assertEqual(payload["state"]["goal"], translated.goal)
                self.assertEqual(payload["questions"]["route"]["criteria"], translated.paths)
                self.assertEqual(payload["questions"]["route"]["instructions"], translations["questions"]["route"])
                self.assertEqual(payload["questions"]["left_risk"]["criteria"], translations["questions"]["risk_criteria"])
                self.assertEqual(set(payload["state"]), {"goal", "situation", "paths"})
        rendered = self.presenter.scene_markdown(GameSession.start([0], "ar"))
        self.assertIn('dir="rtl"', rendered)
        self.assertIn("Round 1", rendered)

    def test_german_catalog_and_payload(self):
        translations = self.localization.catalog("de")
        self.assertEqual(set(translations["scenes"]), {rule.id for rule in SCENE_RULES})
        for index in range(len(self.scenes)):
            original, scene = self.scenes.get(index), self.scenes.get(index, "de")
            with self.subTest(scene=original.id):
                self.assertEqual(scene.best, original.best)
                for key in ("title", "goal", "story", "reason"):
                    self.assertNotEqual(getattr(scene, key), getattr(original, key))
                self.assertEqual(set(scene.paths), set(DIRECTIONS))
                for direction in DIRECTIONS:
                    self.assertNotEqual(scene.paths[direction], original.paths[direction])
                payload = self.client.build_payload(scene)
                self.assertEqual(payload["state"]["paths"], scene.paths)
                for key in ("route", "left_hazard", "left_risk"):
                    self.assertEqual(payload["questions"][key]["instructions"], translations["questions"][key])
                self.assertEqual(payload["questions"]["left_risk"]["criteria"], translations["questions"]["risk_criteria"])
                self.assertEqual([v for _, v in self.presenter.option_choices(scene)], list(DIRECTIONS))
                self.assertTrue(self.presenter.option_choices(scene)[0][0].startswith("Links —"))
        rendered = self.presenter.scene_markdown(GameSession.start([0], "de"))
        self.assertIn("**Links**", rendered)
        self.assertNotIn('dir="rtl"', rendered)
        self.assertIn("Round 1", rendered)

    def test_partial_catalog_falls_back_without_mutating_english(self):
        english = self.localization.catalog("en")
        partial = {
            "directions": {"left": "Links"},
            "questions": {"route": "Translated question"},
            "scenes": {"flooded_valley": {"paths": {"left": "Translated path"}}},
        }
        localization = LocalizationCatalog()
        with patch.object(localization, "_read_catalog", side_effect=lambda code: english if code == "en" else partial):
            scene = localization.localize(SceneRule("flooded_valley", "middle"), "de")
            self.assertEqual(scene.paths["left"], "Translated path")
            self.assertEqual(scene.paths["right"], english["scenes"][scene.id]["paths"]["right"])
            self.assertEqual(scene.goal, english["scenes"][scene.id]["goal"])
            payload = OllamaClient(AppSettings(), localization).build_payload(scene)
            self.assertEqual(payload["questions"]["route"]["instructions"], "Translated question")
            self.assertEqual(payload["questions"]["left_hazard"]["instructions"], english["questions"]["left_hazard"])
            self.assertEqual(localization.catalog("de")["directions"]["middle"], "Middle")
            self.assertEqual(localization.catalog("de")["scenes"]["space_station"], english["scenes"]["space_station"])
            self.assertEqual(localization.catalog("en"), english)
        self.assertEqual(self.scenes.get(0).paths["left"], english["scenes"][scene.id]["paths"]["left"])

    def test_english_catalog_is_complete(self):
        english = self.localization.catalog("en")
        self.assertEqual(set(english["scenes"]), {rule.id for rule in SCENE_RULES})
        self.assertEqual(set(english["directions"]), set(DIRECTIONS))
        for index in range(len(self.scenes)):
            scene = self.scenes.get(index)
            self.assertEqual(scene.goal, english["scenes"][scene.id]["goal"])
            self.assertEqual(self.client.build_payload(scene)["questions"]["route"]["instructions"], english["questions"]["route"])

    def test_english_fallback(self):
        for language in ("en", "unknown"):
            scene = self.scenes.get(0, language)
            self.assertEqual(scene.goal, self.scenes.get(0).goal)
            self.assertEqual(scene.language, "en")
            self.assertIn("Which one", self.client.build_payload(scene)["questions"]["route"]["instructions"])


class SettingsTests(unittest.TestCase):
    def test_environment_is_read_for_each_configuration(self):
        with patch.dict(os.environ, OLLAMA_URL="http://first:1234/", OLLAMA_MODEL="custom", OLLAMA_TIMEOUT="45"):
            first = AppSettings.from_env()
        with patch.dict(os.environ, OLLAMA_URL="http://second:1234", OLLAMA_MODEL="other", OLLAMA_TIMEOUT="90"):
            second = AppSettings.from_env()
        self.assertEqual((first.endpoint, first.model, first.timeout), ("http://first:1234/v1/systemone", "custom", 45))
        self.assertEqual((second.endpoint, second.model, second.timeout), ("http://second:1234/v1/systemone", "other", 90))


if __name__ == "__main__":
    unittest.main()
