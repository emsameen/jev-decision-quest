"""Gradio layout and event wiring."""

import base64
from pathlib import Path

import gradio as gr

from .config import AppSettings
from .game import GameController
from .localization import LANGUAGES, LocalizationCatalog
from .models import GameSession
from .ollama import OllamaClient
from .presentation import GamePresenter
from .scenes import SceneRepository

APP_CSS = Path(__file__).with_name("styles.css").read_text(encoding="utf-8")


class DecisionQuestApp:
    """Compose application services and build the Gradio interface."""

    def __init__(
        self, settings: AppSettings | None = None,
        localization: LocalizationCatalog | None = None,
        client: OllamaClient | None = None,
    ):
        self.settings = settings if settings is not None else AppSettings.from_env()
        self.localization = localization if localization is not None else LocalizationCatalog()
        self.scenes = SceneRepository(self.localization)
        self.client = client if client is not None else OllamaClient(self.settings, self.localization)
        self.presenter = GamePresenter(self.scenes)
        self.controller = GameController(self.settings, self.scenes, self.client, self.presenter)
        self.demo: gr.Blocks | None = None

    def _adventure_banner(self) -> str:
        """Embed the local artwork so the banner works without external services."""
        poster = Path(__file__).resolve().parent.parent / "images" / "poster.png"
        artwork = base64.b64encode(poster.read_bytes()).decode("ascii")
        return (
            '<header class="quest-banner" style="background-image:linear-gradient(90deg,'
            'rgba(3,22,32,.97),rgba(3,22,32,.82) 55%,rgba(3,22,32,.4)),'
            f'url(data:image/png;base64,{artwork})">'
            f'<span class="quest-eyebrow">LOCAL ADVENTURE · {self.settings.rounds} ROUNDS</span>'
            '<h1>Jev Decision <span>Quest</span></h1>'
            '<p>Explore. Learn. Decide.</p>'
            '<div class="quest-intro">Choose your path, ask the model, and discover '
            'how decisions work.</div></header>'
        )

    def build(self) -> gr.Blocks:
        """Build an independent interface with session-local game state."""
        if self.demo is not None:
            return self.demo
        with gr.Blocks(title="Jev Decision Quest · Ollama") as demo, gr.Column(elem_id="quest-app"):
            gr.HTML(self._adventure_banner())
            with gr.Row(elem_id="quest-toolbar"):
                language = gr.Dropdown(
                    choices=LANGUAGES, value="en", label="Question language",
                    info="Applies when you start a new game. Interface stays in English.",
                )
                start = gr.Button("▶ Start Game", variant="primary", scale=0, elem_id="start-game")

            game = gr.State(GameSession())
            with gr.Row(equal_height=False):
                with gr.Column(scale=3, elem_id="quest-scenario"):
                    scene_text = gr.Markdown(
                        "### Your adventure starts here\n\n"
                        "Choose a language and click **Start Game** to discover your first mission.\n\n"
                        "**01 · Read the mission** → **02 · Choose a route** → **03 · Compare decisions**",
                        elem_id="quest-scene",
                    )
                    user_route = gr.Radio(
                        choices=[], label="Which path do you choose?", interactive=False,
                        elem_id="route-choice",
                    )
                    with gr.Row():
                        ask_btn = gr.Button(
                            "▶ Run decision", interactive=False, variant="primary", elem_id="run-decision"
                        )
                        next_btn = gr.Button("Next Round →", interactive=False, elem_id="next-round")
                    status = gr.Markdown(
                        f"🧭 Ready when you are. {self.settings.rounds} missions await.", elem_id="quest-status",
                    )
                with gr.Column(scale=2, elem_id="quest-decisions"):
                    gr.Markdown("### ◈ Decision breakdown")
                    probabilities = gr.HTML(
                        '<div class="quest-empty"><span>◈</span><h3>Your AI field guide</h3>'
                        '<p>Run a decision to reveal route probabilities, a hazard estimate, and a risk score.</p></div>',
                        elem_id="quest-probabilities",
                    )
                    show_debug = gr.Checkbox(label="Show debugging view", value=False)
                    with gr.Column(visible=False) as debug_panel:
                        gr.Markdown("### Round-by-round learning notes")
                        debug_summary = gr.Markdown("_Round summaries will appear after you run the model._")
                        with gr.Accordion("Raw request and response traces", open=False):
                            raw_response = gr.JSON(value=[], label="Model request and response history")
                    with gr.Accordion("How to read the decision", open=False):
                        gr.Markdown(
                            "**How to read the decision**\n"
                            "- **choice:** Selects one route; the bars show probability for each route.\n"
                            "- **Hazard estimate:** `noul` estimates whether the left route states a hazard.\n"
                            "- **Risk rubric:** `score` gives probabilities for each risk level and their expected score.\n\n"
                            "The answer explanation comes from fixed game rules. The model returns structured "
                            "decisions, not natural-language reasoning."
                        )

            outputs = [game, scene_text, user_route, status, probabilities,
                       debug_summary, raw_response, ask_btn, next_btn]
            # All three handlers write the same session state. Serialize them so a
            # restart or queued click cannot race an in-flight model decision.
            start.click(
                self.controller.start_game, inputs=[language], outputs=outputs,
                concurrency_id="game_actions", concurrency_limit=1,
            )
            ask_btn.click(self.controller.resolve_round, inputs=[game, user_route], outputs=outputs,
                          concurrency_id="game_actions", concurrency_limit=1)
            next_btn.click(
                self.controller.next_round, inputs=[game], outputs=outputs,
                concurrency_id="game_actions", concurrency_limit=1,
            )
            user_route.change(
                self.controller.select_route,
                inputs=[user_route], outputs=[ask_btn], queue=False,
            )
            show_debug.change(
                self.controller.toggle_debug,
                inputs=[show_debug], outputs=[debug_panel], queue=False,
            )
            gr.Markdown(
                f"🧭 **Local game** · {self.settings.rounds} missions · "
                f"Powered by Ollama `{self.settings.model}` · "
                "Explanations follow fixed game rules.", elem_id="quest-footer",
            )
        self.demo = demo
        return demo

    def launch(self, **kwargs):
        """Start the local interface with its stylesheet and optional launch overrides."""
        options = {"server_name": "127.0.0.1", "server_port": 7860, "css": APP_CSS}
        options.update(kwargs)
        return self.build().launch(**options)


def create_app() -> gr.Blocks:
    """Convenience factory for callers that only need the Gradio Blocks object."""
    return DecisionQuestApp().build()
