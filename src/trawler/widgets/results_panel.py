from __future__ import annotations

import subprocess

from rich.rule import Rule
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
        # Search results — persistent scrollback
        self._buffer: list[str] = []
        self._last_command_offset: int = 0
        # Utility output (config / help) — separate, ephemeral
        self._utility_buffer: list[str] = []
        self._utility_mode: bool = False

    def compose(self) -> ComposeResult:
        yield RichLog(id="results-log", markup=True, highlight=False, wrap=True)
        yield RichLog(id="utility-log", markup=True, highlight=False, wrap=True)
        yield Static("", id="stream-area")

    def on_mount(self) -> None:
        self.query_one("#utility-log", RichLog).display = False

    # ------------------------------------------------------------------
    # Mode switching — search vs utility (config / help)
    # ------------------------------------------------------------------

    def show_search(self) -> None:
        """Switch to the persistent search results log."""
        self.query_one("#results-log", RichLog).display = True
        self.query_one("#utility-log", RichLog).display = False
        self._utility_mode = False

    def show_utility(self) -> None:
        """Switch to the utility log and clear it for fresh output."""
        self.query_one("#results-log", RichLog).display = False
        log = self.query_one("#utility-log", RichLog)
        log.clear()
        log.display = True
        self._utility_buffer.clear()
        self._utility_mode = True

    # ------------------------------------------------------------------
    # Writing — routed by current mode
    # ------------------------------------------------------------------

    def write(self, text: str) -> None:
        if self._utility_mode:
            self.query_one("#utility-log", RichLog).write(text)
            self._utility_buffer.append(_strip_markup(text))
        else:
            self.query_one("#results-log", RichLog).write(text)
            self._buffer.append(_strip_markup(text))

    def write_header(self, command: str) -> None:
        if self._utility_mode:
            self.query_one("#utility-log", RichLog).write(
                Rule(f"[bold cyan]{command}[/]", style="dim", align="left")
            )
            self._utility_buffer.append(f"─── {command} ───")
        else:
            self.query_one("#results-log", RichLog).write(
                Rule(f"[bold cyan]{command}[/]", style="dim", align="left")
            )
            self._buffer.append(f"─── {command} ───")

    def mark_command_start(self) -> None:
        """Record the current buffer length so /ask can extract only the latest output."""
        if self._buffer:
            log = self.query_one("#results-log", RichLog)
            log.write("")
            log.write("")
            self._buffer.extend(["", ""])
        self._last_command_offset = len(self._buffer)

    def last_command_context(self) -> str:
        """Return the text written since the last mark_command_start() call."""
        return "\n".join(self._buffer[self._last_command_offset:])

    def clear(self) -> None:
        """Clear the search results log (used by /reset only)."""
        self.query_one("#results-log", RichLog).clear()
        self._buffer.clear()
        self._last_command_offset = 0

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
            self.query_one("#results-log", RichLog).write(Text(final_text))
            self._buffer.append(final_text)

    def copy_to_clipboard(self) -> bool:
        """Copy the currently visible log to clipboard via pbcopy."""
        buf = self._utility_buffer if self._utility_mode else self._buffer
        text = "\n".join(buf)
        try:
            subprocess.run(["pbcopy"], input=text.encode(), check=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False
