from __future__ import annotations

import subprocess

from rich.text import Text
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import RichLog, Static


def _strip_markup(text: str) -> str:
    try:
        return Text.from_markup(text).plain
    except Exception:
        return text


class ResultsPanel(Widget):
    DEFAULT_CSS = """
    ResultsPanel {
        border: solid $primary;
        layout: vertical;
    }
    ResultsPanel RichLog {
        padding: 0 1;
        height: 1fr;
    }
    ResultsPanel #stream-area {
        display: none;
        padding: 0 1;
        height: auto;
        max-height: 50%;
        border-top: solid $primary-darken-3;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._buffer: list[str] = []

    def compose(self) -> ComposeResult:
        yield RichLog(id="results-log", markup=True, highlight=False, wrap=True)
        yield Static("", id="stream-area")

    def write(self, text: str) -> None:
        self.query_one(RichLog).write(text)
        self._buffer.append(_strip_markup(text))

    def write_header(self, command: str) -> None:
        log = self.query_one(RichLog)
        log.write(f"[bold dim]─── {command} ───[/]")
        self._buffer.append(f"─── {command} ───")

    def clear(self) -> None:
        self.query_one(RichLog).clear()
        self._buffer.clear()

    # ------------------------------------------------------------------
    # Streaming support for /ask
    # ------------------------------------------------------------------

    def start_stream(self) -> None:
        area = self.query_one("#stream-area", Static)
        area.update("")
        area.display = True

    def update_stream(self, text: str) -> None:
        self.query_one("#stream-area", Static).update(Text(text))

    def end_stream(self, final_text: str) -> None:
        area = self.query_one("#stream-area", Static)
        area.display = False
        area.update("")
        if final_text:
            self.query_one(RichLog).write(Text(final_text))
            self._buffer.append(final_text)

    def copy_to_clipboard(self) -> bool:
        """Copy all results to clipboard via pbcopy. Returns True on success."""
        text = "\n".join(self._buffer)
        try:
            subprocess.run(["pbcopy"], input=text.encode(), check=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False
