from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.suggester import Suggester
from textual.widget import Widget
from textual.widgets import Input, Label

COMMANDS = [
    "/search",
    "/rg",
    "/yara",
    "/semantic",
    "/index",
    "/config",
    "/config add",
    "/config rm",
    "/config filesize",
    "/config ext list",
    "/config ext add",
    "/config ext rm",
    "/config ext reset",
    "/config rules",
    "/config rules reset",
    "/reset",
    "/help",
    "/exit",
]

_PATH_PREFIX = "/config add "


class CommandSuggester(Suggester):
    """Command completion, with path completion after '/config add '."""

    def __init__(self) -> None:
        # case_sensitive=True so get_suggestion receives the original value
        # unchanged — critical for correct path operations on case-sensitive
        # or symlinked filesystems (e.g. macOS /Users vs /users).
        super().__init__(use_cache=False, case_sensitive=True)

    async def get_suggestion(self, value: str) -> str | None:
        if value.lower().startswith(_PATH_PREFIX.lower()):
            path_part = value[len(_PATH_PREFIX):]
            if not path_part:
                return None
            p = Path(path_part)
            try:
                if path_part.endswith("/") and p.is_dir():
                    # Completed dir — suggest first child
                    children = sorted(
                        d.name for d in p.iterdir()
                        if d.is_dir() and not d.name.startswith(".")
                    )
                    if not children:
                        return None
                    return _PATH_PREFIX + path_part + children[0] + "/"
                else:
                    # Partial name — complete against siblings
                    parent = p.parent
                    name_prefix = p.name
                    children = sorted(
                        d.name for d in parent.iterdir()
                        if d.is_dir()
                        and d.name.startswith(name_prefix)
                        and d.name != name_prefix
                        and not (not name_prefix and d.name.startswith("."))
                    )
                    if not children:
                        return None
                    return _PATH_PREFIX + str(parent / children[0]) + "/"
            except (PermissionError, OSError):
                return None

        lower = value.lower()
        for cmd in COMMANDS:
            if cmd.startswith(lower) and cmd != lower:
                return cmd
        return None


class CommandBar(Widget):
    DEFAULT_CSS = """
    CommandBar {
        height: 3;
        background: $surface;
        padding: 0 1;
    }
    CommandBar Horizontal {
        height: 3;
        align: left middle;
    }
    CommandBar Label {
        width: auto;
        color: $accent;
        text-style: bold;
        height: 3;
        content-align: left middle;
        padding: 0 1 0 0;
    }
    CommandBar Input {
        width: 1fr;
    }
    """

    class Submitted(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label(">")
            yield Input(
                placeholder="/search  /rg  /yara  /semantic  /index  /config  /help  /exit",
                id="cmd-input",
                suggester=CommandSuggester(),
            )

    def on_key(self, event) -> None:
        if event.key == "tab":
            event.prevent_default()
            event.stop()
            self.query_one(Input).action_cursor_right()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.post_message(self.Submitted(event.value.strip()))
        event.input.value = ""

    def focus_input(self) -> None:
        self.query_one(Input).focus()
