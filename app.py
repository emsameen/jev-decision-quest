"""Launch Decision Quest with ``python app.py``."""

from decision_quest.ui import DecisionQuestApp

app = DecisionQuestApp()
demo = app.build()

if __name__ == "__main__":
    app.launch()
