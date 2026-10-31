"""Gradio layout and event wiring."""

import gradio as gr

from .config import MODEL, MODE_DUEL, MODE_PREDICT, MODE_WATCH
from .game import next_round, resolve_round, start_game
from .localization import LANGUAGES


def create_app() -> gr.Blocks:
    """Build an independent interface with session-local game state."""
    with gr.Blocks(title="Decision Quest · Nimble + Ollama") as demo:
        gr.Markdown(
            "# 🧭 Decision Quest\n"
            "**Learn Jev-style decision models through a five-round adventure.** "
            f"Powered by local Ollama `{MODEL}`; no LLM-generated stories or chat responses."
        )
        with gr.Row():
            mode = gr.Radio(
                [MODE_PREDICT, MODE_DUEL, MODE_WATCH],
                value=MODE_PREDICT,
                label="Select game mode",
                info=("Predict = guess the model's choice; Human vs Nimble = score safe routes; "
                      "Watch = inspect the AI's choices."),
            )
            language = gr.Dropdown(
                choices=LANGUAGES, value="en", label="Question language",
                info="Applies when you start a new game. Interface stays in English.",
            )
            start = gr.Button("▶ Start Game", variant="primary", scale=0)

        game = gr.State({})
        with gr.Row(equal_height=False):
            with gr.Column(scale=3):
                scene_text = gr.Markdown("Choose a mode and click **Start Game**.")
                user_route = gr.Radio(choices=[], label="Which path do you choose?", interactive=False)
                with gr.Row():
                    ask_btn = gr.Button("🤖 Ask Nimble", interactive=False, variant="primary")
                    next_btn = gr.Button("Next Round →", interactive=False)
                status = gr.Markdown("No game in progress.")
            with gr.Column(scale=2):
                gr.Markdown("### Nimble's probabilities")
                probabilities = gr.HTML("<p>Start a game to inspect model decisions.</p>")
                show_debug = gr.Checkbox(label="Show debugging view", value=False)
                with gr.Column(visible=False) as debug_panel:
                    gr.Markdown("### Model request and response history")
                    raw_response = gr.JSON(value=[], label="Requests, responses, and errors")
                gr.Markdown(
                    "**What you're learning**\n"
                    "- `choice`: Select among routes, with probabilities.\n"
                    "- `noul`: Yes/no probability for a hazard.\n"
                    "- `score`: Rate left-route risk on an ordered scale.\n\n"
                    "Nimble selects from given answers; it does **not** generate explanations. "
                    "The route reasoning shown here comes from fixed game rules."
                )

        outputs = [game, scene_text, user_route, status, probabilities,
                   raw_response, ask_btn, next_btn]
        # All three handlers write the same session state. Serialize them so a
        # restart or queued click cannot race an in-flight model decision.
        game_events = dict(concurrency_id="game_actions", concurrency_limit=1)
        start.click(start_game, inputs=[mode, language], outputs=outputs, **game_events)
        ask_btn.click(resolve_round, inputs=[game, mode, user_route], outputs=outputs,
                      **game_events)
        next_btn.click(next_round, inputs=[game, mode], outputs=outputs, **game_events)
        show_debug.change(
            lambda visible: gr.update(visible=visible),
            inputs=[show_debug], outputs=[debug_panel], queue=False,
        )
    return demo
