"""Launch Decision Quest with ``python app.py``."""

from decision_quest.ui import APP_CSS, create_app

demo = create_app()

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860, css=APP_CSS)
