from __future__ import annotations

import subprocess

from rich.text import Text
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import RichLog


def _strip_markup(text: str) -> str:
    try:
        return Text.from_markup(text).plain
    except Exception:
        return text


class ResultsPanel(Widget):
    DEFAULT_CSS = """
    ResultsPanel {
        border: solid $primary;
    }
    ResultsPanel RichLog {
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._buffer: list[str] = []

    def compose(self) -> ComposeResult:
        yield RichLog(id="results-log", markup=True, highlight=False, wrap=True)

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

    def copy_to_clipboard(self) -> bool:
        """Copy all results to clipboard via pbcopy. Returns True on success."""
        text = "\n".join(self._buffer)
        try:
            subprocess.run(["pbcopy"], input=text.encode(), check=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False
