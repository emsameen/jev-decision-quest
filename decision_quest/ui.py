"""Gradio layout and event wiring."""

import gradio as gr

from .config import DIRECTIONS, MODEL
from .game import next_round, resolve_round, start_game
from .localization import LANGUAGES

APP_CSS = (
    "#start-game, #run-decision, #next-round { min-height: 52px !important; "
    "font-size: 1.05rem !important; }"
    "#route-choice label { min-height: 52px !important; padding: 12px 16px !important; }"
)


def create_app() -> gr.Blocks:
    """Build an independent interface with session-local game state."""
    with gr.Blocks(title="Jev Decision Quest · Ollama") as demo:
        gr.Markdown(
            "# 🧭 Jev Decision Quest\n"
            "**Learn Jev-style decision models through a five-round adventure.** "
            f"Powered by local Ollama `{MODEL}`; no LLM-generated stories or chat responses."
        )
        with gr.Row():
            language = gr.Dropdown(
                choices=LANGUAGES, value="en", label="Question language",
                info="Applies when you start a new game. Interface stays in English.",
            )
            start = gr.Button("▶ Start Game", variant="primary", scale=0, elem_id="start-game")

        game = gr.State({})
        with gr.Row(equal_height=False):
            with gr.Column(scale=3):
                scene_text = gr.Markdown("Choose a question language and click **Start Game**.")
                user_route = gr.Radio(
                    choices=[], label="Which path do you choose?", interactive=False,
                    elem_id="route-choice",
                )
                with gr.Row():
                    ask_btn = gr.Button(
                        "▶ Run decision", interactive=False, variant="primary", elem_id="run-decision"
                    )
                    next_btn = gr.Button("Next Round →", interactive=False, elem_id="next-round")
                status = gr.Markdown("No game in progress.")
            with gr.Column(scale=2):
                gr.Markdown("### Decision breakdown")
                probabilities = gr.HTML("<p>Start a game to inspect all three decision types.</p>")
                show_debug = gr.Checkbox(label="Show debugging view", value=False)
                with gr.Column(visible=False) as debug_panel:
                    gr.Markdown("### Round-by-round learning notes")
                    debug_summary = gr.Markdown("_Round summaries will appear after you run the model._")
                    with gr.Accordion("Raw request and response traces", open=False):
                        raw_response = gr.JSON(value=[], label="Model request and response history")
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
            start_game, inputs=[language], outputs=outputs,
            concurrency_id="game_actions", concurrency_limit=1,
        )
        ask_btn.click(resolve_round, inputs=[game, user_route], outputs=outputs,
                      concurrency_id="game_actions", concurrency_limit=1)
        next_btn.click(
            next_round, inputs=[game], outputs=outputs,
            concurrency_id="game_actions", concurrency_limit=1,
        )
        user_route.change(
            lambda choice: gr.update(interactive=choice in DIRECTIONS),
            inputs=[user_route], outputs=[ask_btn], queue=False,
        )
        show_debug.change(
            lambda visible: gr.update(visible=visible),
            inputs=[show_debug], outputs=[debug_panel], queue=False,
        )
    return demo
