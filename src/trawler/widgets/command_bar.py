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
    "/ask",
    "/config",
    "/config path",
    "/config path add",
    "/config path rm",
    "/config filesize",
    "/config ext list",
    "/config ext add",
    "/config ext rm",
    "/config ext reset",
    "/config rules",
    "/config rules reset",
    "/config proxy",
    "/config proxy reset",
    "/config llm",
    "/config llm mlx",
    "/config llm gguf",
    "/config llm remote",
    "/config llm apikey",
    "/config llm systemprompt",
    "/config llm systemprompt reset",
    "/config llm reset",
    "/reset",
    "/help",
    "/exit",
]

_PATH_PREFIX = "/config path add "
_RM_PREFIX = "/config path rm "
_DIR_FLAG = " --dir "


def _complete_fs_path(path_part: str) -> str | None:
    """Return a completed filesystem path for *path_part*, or None.

    Appends '/' to completed directory names so the user can keep tabbing
    deeper without needing to type the separator themselves.
    """
    if not path_part:
        return None
    p = Path(path_part)
    try:
        sep = "/" if not path_part.startswith("\\") else "\\"
        if path_part.endswith(("/", "\\")) and p.is_dir():
            # Completed dir — suggest first child
            children = sorted(
                d.name for d in p.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            )
            if not children:
                return None
            return path_part + children[0] + sep
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
            return str(parent / children[0]) + sep
    except (PermissionError, OSError):
        return None


class CommandSuggester(Suggester):
    """Command completion with path completion for add/rm/--dir args."""

    def __init__(self, get_dirs=None) -> None:
        # case_sensitive=True so get_suggestion receives the original value
        # unchanged — critical for correct path operations on case-sensitive
        # or symlinked filesystems (e.g. macOS /Users vs /users).
        super().__init__(use_cache=False, case_sensitive=True)
        # Optional callable returning the list of configured directories,
        # used to autocomplete '/config path rm <partial-path>'.
        self._get_dirs = get_dirs

    async def get_suggestion(self, value: str) -> str | None:
        # --- /config path rm: complete from configured dirs ---------------
        if value.lower().startswith(_RM_PREFIX.lower()) and self._get_dirs:
            typed = value[len(_RM_PREFIX):]
            try:
                dirs = self._get_dirs()
            except Exception:
                dirs = []
            for d in dirs:
                if d.startswith(typed) and d != typed:
                    return _RM_PREFIX + d
            return None

        # --- /config path add: filesystem completion ----------------------
        if value.lower().startswith(_PATH_PREFIX.lower()):
            path_part = value[len(_PATH_PREFIX):]
            completed = _complete_fs_path(path_part)
            if completed is None:
                return None
            return _PATH_PREFIX + completed

        # --- --dir <path>: cycle through configured directories -------------
        # Find the last occurrence of " --dir " in the typed value so that
        # completion works regardless of what comes before the flag.
        lower = value.lower()
        dir_flag_pos = lower.rfind(_DIR_FLAG.lower())
        if dir_flag_pos != -1 and self._get_dirs:
            prefix = value[:dir_flag_pos + len(_DIR_FLAG)]
            path_part = value[len(prefix):]
            # Strip surrounding quotes so matching works against raw dir paths
            stripped = path_part.strip('"').strip("'")
            try:
                dirs = self._get_dirs()
            except Exception:
                dirs = []
            if not dirs:
                return None

            def _quote(d: str) -> str:
                return f'"{d}"' if " " in d else d

            # Empty path part → suggest first configured dir
            if not stripped:
                return prefix + _quote(dirs[0])
            # Exact match → cycle to next configured dir
            try:
                idx = dirs.index(stripped)
                next_dir = dirs[(idx + 1) % len(dirs)]
                if next_dir == stripped:
                    return None
                return prefix + _quote(next_dir)
            except ValueError:
                pass
            # Partial match → suggest first configured dir that starts with it
            for d in dirs:
                if d.startswith(stripped) and d != stripped:
                    return prefix + _quote(d)
            return None

        # --- command keyword completion ------------------------------------
        for cmd in COMMANDS:
            if cmd.startswith(lower) and cmd != lower:
                # Never return a suggestion whose ghost text starts with a space.
                # Textual's inline completion would consume the space keypress as
                # "matching the ghost" rather than inserting it into the input.
                ghost = cmd[len(value):]
                if ghost.startswith(" "):
                    continue
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

    def on_mount(self) -> None:
        self._history: list[str] = []
        self._history_idx: int = 0   # points one past the end when not navigating
        self._draft: str = ""         # preserves in-progress text during history nav

    def _get_config_dirs(self) -> list[str]:
        """Return configured directories for rm autocomplete."""
        try:
            return list(self.app.config.directories)  # type: ignore[attr-defined]
        except Exception:
            return []

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label(">")
            yield Input(
                placeholder="/search  /rg  /yara  /semantic  /index  /ask  /config  /help  /exit",
                id="cmd-input",
                suggester=CommandSuggester(get_dirs=self._get_config_dirs),
            )

    def on_key(self, event) -> None:
        inp = self.query_one(Input)
        if event.key == "tab":
            event.prevent_default()
            event.stop()
            inp.action_cursor_right()
        elif event.key == "space":
            # On some terminals (e.g. Windows), the space key arrives with
            # character=None so Input treats it as non-printable and never
            # inserts it.  Handle it explicitly here so the space always
            # reaches the input field regardless of terminal.
            event.prevent_default()
            event.stop()
            inp.insert_text_at_cursor(" ")
        elif event.key == "up":
            if not self._history:
                return
            event.prevent_default()
            event.stop()
            # Save whatever the user has typed before entering history nav
            if self._history_idx == len(self._history):
                self._draft = inp.value
            if self._history_idx > 0:
                self._history_idx -= 1
                inp.value = self._history[self._history_idx]
                inp.cursor_position = len(inp.value)
        elif event.key == "down":
            if self._history_idx >= len(self._history):
                return
            event.prevent_default()
            event.stop()
            self._history_idx += 1
            if self._history_idx == len(self._history):
                inp.value = self._draft
            else:
                inp.value = self._history[self._history_idx]
            inp.cursor_position = len(inp.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if text:
            # Skip consecutive duplicates (like bash HISTCONTROL=ignoredups)
            if not self._history or self._history[-1] != text:
                self._history.append(text)
        self._history_idx = len(self._history)
        self._draft = ""
        self.post_message(self.Submitted(text))
        event.input.value = ""

    def focus_input(self) -> None:
        self.query_one(Input).focus()

    def set_busy(self, busy: bool) -> None:
        inp = self.query_one(Input)
        inp.disabled = busy
        inp.placeholder = "waiting for LLM…" if busy else "/search  /rg  /yara  /semantic  /index  /ask  /config  /help  /exit"
        if not busy:
            inp.focus()
