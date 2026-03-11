from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.suggester import Suggester
from textual.widgets import Button, Header, Input, Label
from textual._work_decorator import work


class PathSuggester(Suggester):
    """Tab-complete directory paths in path input fields."""

    async def get_suggestion(self, value: str) -> str | None:
        if not value:
            return None
        p = Path(value)
        parent = p if p.is_dir() else p.parent
        try:
            matches = sorted(
                str(d) + "/"
                for d in parent.iterdir()
                if d.is_dir() and str(d).startswith(value) and str(d) != value
            )
            return matches[0] if matches else None
        except (PermissionError, OSError):
            return None

from .config import TrawlerConfig
from .index_state import IndexState
from .search import basic, ripgrep, yara_scan
from .search import semantic as semantic_search
from .widgets.command_bar import CommandBar
from .widgets.results_panel import ResultsPanel
from .widgets.sidebar import DirectorySidebar
from .widgets.status_bar import StatusBar

# ---------------------------------------------------------------------------
# Command tree for hierarchical help (Phase 5)
# ---------------------------------------------------------------------------
COMMAND_TREE: dict = {
    "/search":   {
        "help": "Regex line scan across configured dirs (Python re syntax). Supports PDF and DOCX via text extraction.",
        "args": "<pattern> [--dir <path>]",
        "notes": [
            "Inline flags use Python regex syntax:",
            "  (?i)          — case-insensitive  e.g. /search (?i)password",
            "  (?m)          — multiline anchors (^ / $ per line)",
            "  (?i)(?m)      — combine flags freely",
            "  (?s)          — dot matches newline",
            "--dir <path>  — limit search to one configured directory",
            "PDF and DOCX files are text-extracted before scanning.",
            "/rg is faster for large plain-text datasets; use /search for PDF/DOCX.",
        ],
    },
    "/rg":       {
        "help": "Ripgrep search (text files only — no PDF/DOCX). Last token is the pattern; flags precede it.",
        "args": "[opts] <pattern> [--dir <path>]",
        "notes": [
            "Supported flags:",
            "  -i / --ignore-case   — case-insensitive match",
            "  -m / --multiline     — multiline mode",
            "--dir <path>  — limit search to one configured directory",
            "Note: PDF/DOCX are treated as binary by ripgrep — use /search for those.",
        ],
    },
    "/yara":     {
        "help": "Run YARA rules against configured dirs. Matches raw file bytes (not text-extracted).",
        "args": "[rule-glob] [--dir <path>]",
        "notes": [
            "rule-glob filters by rule NAME (not filename) using fnmatch glob syntax:",
            "  /yara            — run all rules",
            "  /yara *cred*     — rules whose name contains 'cred'",
            "  /yara pii_*      — rules whose name starts with 'pii_'",
            "Rules live in src/trawler/rules/ (or custom path via /config rules <path>).",
            "--dir <path>  — limit scan to one configured directory",
            "YARA scans raw bytes: works on text-layer PDFs but not DOCX (compressed).",
        ],
    },
    "/semantic": {"help": "Vector similarity search (requires /index first)", "args": "<query> [--dir <path>]"},
    "/index":    {"help": "Embed and index configured dirs into ChromaDB"},
    "/ask":      {"help": "Ask a local or remote LLM about current results", "args": "<question>"},
    "/reset":    {"help": "Clear vector store & index history (requires confirmation)"},
    "/help":     {"help": "Show help", "args": "[command]"},
    "/exit":     {"help": "Exit trawler"},
    "/config": {
        "help": "View or change configuration",
        "subcommands": {
            "path": {
                "help": "Manage watched directories",
                "subcommands": {
                    "add": {"help": "Add a directory to watch", "args": "<path>"},
                    "rm":  {"help": "Remove a watched directory", "args": "<path>"},
                },
            },
            "list":     {"help": "List configured directories and settings"},
            "filesize": {"help": "Set max file size for indexing", "args": "<value|0=unlimited>"},
            "rules":    {"help": "Set custom YARA rules directory", "args": "<path>|reset"},
            "proxy":    {"help": "Set HTTP proxy for model downloads", "args": "<url>|reset"},
            "ext": {
                "help": "Manage file extension filters",
                "subcommands": {
                    "list":  {"help": "Show current index/skip extension lists"},
                    "add":   {"help": "Add extension to index whitelist", "args": "<.ext>"},
                    "rm":    {"help": "Move extension to skip list", "args": "<.ext>"},
                    "reset": {"help": "Restore default extension lists"},
                },
            },
            "llm": {
                "help": "Configure local or remote LLM for /ask",
                "subcommands": {
                    "mlx <hf-repo-id>":         {"help": "Apple Silicon — HuggingFace repo ID, downloaded automatically"},
                    "gguf <path>":              {"help": "Cross-platform — local path to a .gguf file"},
                    "remote <url>":             {"help": "Base URL of remote OpenAI-compatible endpoint"},
                    "remote <url> <model>":     {"help": "Remote endpoint base URL + model name"},
                    "apikey <key>":             {"help": "Set API key for remote endpoint"},
                    "systemprompt <text>":      {"help": "Set system prompt"},
                    "systemprompt reset":       {"help": "Remove system prompt"},
                    "reset":                    {"help": "Disable LLM"},
                },
            },
        },
    },
}

# (description, recommended_to_index)
EXTENSION_NOTES: dict[str, tuple[str, bool]] = {
    ".json":   ("structured data — poor semantic value", False),
    ".csv":    ("tabular data — poor semantic value", False),
    ".tsv":    ("tabular data — poor semantic value", False),
    ".xml":    ("structured markup — poor semantic value", False),
    ".sql":    ("SQL dump — poor semantic value", False),
    ".db":     ("database file — binary/structured", False),
    ".sqlite": ("database file — binary/structured", False),
    ".log":    ("log file — may contain useful text", True),
    ".txt":    ("plain text — good semantic content", True),
    ".md":     ("Markdown — good semantic content", True),
    ".rst":    ("reStructuredText — good semantic content", True),
    ".html":   ("HTML document — good semantic content", True),
    ".htm":    ("HTML document — good semantic content", True),
    ".eml":    ("email message — good semantic content", True),
    ".mbox":   ("email mailbox — good semantic content", True),
    ".yaml":   ("YAML config/data — poor semantic value", False),
    ".yml":    ("YAML config/data — poor semantic value", False),
    ".pdf":    ("PDF — text extraction not supported", False),
    ".py":     ("Python source — moderate semantic value", True),
    ".sh":     ("shell script — moderate semantic value", True),
    ".env":    ("environment file — sensitive, poor semantic value", False),
    ".ini":    ("config file — poor semantic value", False),
    ".conf":   ("config file — poor semantic value", False),
    ".toml":   ("TOML config — poor semantic value", False),
}


def _parse_file_size(value: str) -> int | None:
    """Parse '500KB', '2MB', '0' etc → bytes. 0 = no limit. None = parse error."""
    raw = value.strip().upper()
    try:
        if raw in ("0", "NONE", "UNLIMITED"):
            return 0
        if raw.endswith("GB"):
            return int(float(raw[:-2]) * 1024 * 1024 * 1024)
        if raw.endswith("MB"):
            return int(float(raw[:-2]) * 1024 * 1024)
        if raw.endswith("KB"):
            return int(float(raw[:-2]) * 1024)
        return int(float(raw) * 1024)  # bare number = KB
    except ValueError:
        return None



class ConfirmResetModal(ModalScreen[bool]):
    """Requires the user to type 'reset' before wiping the vector store."""

    DEFAULT_CSS = """
    ConfirmResetModal {
        align: center middle;
    }
    ConfirmResetModal #dialog {
        width: 60;
        height: 14;
        border: solid $error;
        background: $surface;
        padding: 1 2;
    }
    ConfirmResetModal Label {
        margin-bottom: 1;
    }
    ConfirmResetModal Input {
        margin-bottom: 1;
    }
    ConfirmResetModal #buttons {
        height: 3;
        align: right middle;
    }
    ConfirmResetModal Button {
        margin-left: 1;
    }
    """

    def compose(self) -> ComposeResult:
        from textual.containers import Vertical, Horizontal as HBox
        with Vertical(id="dialog"):
            yield Label("[bold red]Reset Vector Store[/]", markup=True)
            yield Label(
                "This will permanently delete the ChromaDB index\n"
                "and all indexing history. This cannot be undone.\n\n"
                '[dim]Type [bold]"reset"[/bold] to confirm.[/]',
                markup=True,
            )
            yield Input(placeholder="reset", id="confirm-input")
            with HBox(id="buttons"):
                yield Button("Cancel", variant="default", id="cancel")
                yield Button("Reset", variant="error", id="confirm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            val = self.query_one("#confirm-input", Input).value.strip().lower()
            self.dismiss(val == "reset")
        else:
            self.dismiss(False)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        val = event.value.strip().lower()
        self.dismiss(val == "reset")

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)


class FileSizeLimitModal(ModalScreen[int | None]):
    """First-run prompt to set a maximum file size for indexing."""

    DEFAULT_CSS = """
    FileSizeLimitModal {
        align: center middle;
    }
    FileSizeLimitModal #dialog {
        width: 64;
        height: 17;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    FileSizeLimitModal Label {
        margin-bottom: 1;
    }
    FileSizeLimitModal Input {
        margin-bottom: 1;
    }
    FileSizeLimitModal #buttons {
        height: 3;
        align: right middle;
    }
    FileSizeLimitModal Button {
        margin-left: 1;
    }
    """

    def compose(self) -> ComposeResult:
        from textual.containers import Vertical, Horizontal as HBox
        with Vertical(id="dialog"):
            yield Label("[bold]Set File Size Limit[/]", markup=True)
            yield Label(
                "Files larger than this will be skipped during indexing.\n"
                "It is strongly recommended to keep this value small \n"
                "to avoid overwhelming your system's memory and disk, \n"
                "and to keep processing time as short as possible. Only \n"
                "index large files if you have to.\n"
                "\n"
                "[dim]Enter size in KB (e.g. 500 = 500 KB, 2048 = 2 MB)[/]",
                markup=True,
            )
            yield Input(value="500", id="size-input")
            with HBox(id="buttons"):
                yield Button("Cancel", variant="default", id="cancel")
                yield Button("No Limit", variant="warning", id="no-limit")
                yield Button("Set Limit", variant="primary", id="confirm")

    def _parse(self) -> int:
        raw = self.query_one("#size-input", Input).value.strip().upper()
        try:
            if raw.endswith("MB"):
                return int(float(raw[:-2]) * 1024 * 1024)
            if raw.endswith("KB"):
                return int(float(raw[:-2]) * 1024)
            return int(float(raw) * 1024)  # bare number treated as KB
        except ValueError:
            return 500 * 1024

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            self.dismiss(self._parse())
        elif event.button.id == "no-limit":
            self.dismiss(0)
        else:
            self.dismiss(None)

    def on_input_submitted(self, _: Input.Submitted) -> None:
        self.dismiss(self._parse())

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


class ExtensionModal(ModalScreen):
    """Prompt user to categorise newly discovered file extensions."""

    DEFAULT_CSS = """
    ExtensionModal {
        align: center middle;
    }
    ExtensionModal #dialog {
        width: 70;
        height: 24;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    ExtensionModal Label {
        margin-bottom: 1;
    }
    ExtensionModal SelectionList {
        height: 1fr;
        border: solid $panel;
        margin-bottom: 1;
    }
    ExtensionModal #buttons {
        height: 3;
        align: right middle;
    }
    ExtensionModal Button {
        margin-left: 1;
    }
    """

    def __init__(self, unknown_exts: list[str]) -> None:
        super().__init__()
        self.unknown_exts = unknown_exts

    def compose(self) -> ComposeResult:
        from textual.containers import Vertical, Horizontal as HBox
        from textual.widgets import SelectionList
        from textual.widgets.selection_list import Selection

        selections = []
        for ext in self.unknown_exts:
            desc, recommended = EXTENSION_NOTES.get(ext, ("unknown format — embed at your own risk", False))
            selections.append(Selection(f"{ext}  — {desc}", ext, recommended))

        with Vertical(id="dialog"):
            yield Label("[bold]New File Types Discovered[/]", markup=True)
            yield Label(
                "Select extensions to add to your index whitelist.\n"
                "Unselected types will be permanently skipped.\n"
                "[dim]You can change this later with /config ext add/rm[/]",
                markup=True,
            )
            yield SelectionList(*selections, id="ext-list")
            with HBox(id="buttons"):
                yield Button("Cancel", variant="default", id="cancel")
                yield Button("Skip All", variant="warning", id="skip-all")
                yield Button("Save & Continue", variant="primary", id="confirm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        from textual.widgets import SelectionList as SL
        if event.button.id == "confirm":
            selected = list(self.query_one(SL).selected)
            to_whitelist = [e for e in self.unknown_exts if e in selected]
            to_skip = [e for e in self.unknown_exts if e not in selected]
            self.dismiss((to_whitelist, to_skip))
        elif event.button.id == "skip-all":
            self.dismiss(([], self.unknown_exts))
        else:
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


class TrawlerApp(App):
    TITLE = "Trawler"
    SUB_TITLE = "Data triage tool"

    CSS = """
    Screen {
        layout: vertical;
    }
    #main-area {
        height: 1fr;
    }
    DirectorySidebar {
        width: 42;
    }
    ResultsPanel {
        width: 1fr;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+y", "copy_results", "Copy results", show=True),
        Binding("escape", "focus_command", "Focus input", show=False),
    ]

    def __init__(self) -> None:
        import threading
        super().__init__()
        self.config = TrawlerConfig.load()
        self._apply_proxy(self.config.proxy)
        self.index_state = IndexState()
        self._indexing = False
        self._searching = False
        self._stop_index = threading.Event()
        self._stop_search = threading.Event()
        self._stop_ask = threading.Event()

    @staticmethod
    def _apply_proxy(proxy: str | None) -> None:
        import os
        if proxy:
            os.environ["HTTP_PROXY"] = proxy
            os.environ["HTTPS_PROXY"] = proxy
        else:
            os.environ.pop("HTTP_PROXY", None)
            os.environ.pop("HTTPS_PROXY", None)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-area"):
            yield DirectorySidebar(self.config)
            yield ResultsPanel()
        yield StatusBar()
        yield CommandBar()

    @property
    def status(self) -> StatusBar:
        return self.query_one(StatusBar)

    def on_mount(self) -> None:
        self.query_one(CommandBar).focus_input()
        self._show_home()
        self.status.set_hint("Press Enter to return home")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "cmd-input":
            if event.value:
                self.status._reset()
            else:
                self.status.set_hint("Press Enter to return home")

    # ------------------------------------------------------------------
    # Help system
    # ------------------------------------------------------------------

    def _show_help(self, path: list[str] | None = None) -> None:
        """Show help. With no path shows the welcome/help screen; with path walks COMMAND_TREE."""
        results = self.query_one(ResultsPanel)
        results.show_utility()
        if not path:
            self._write_help_content(results)
            return

        # Normalise first token: "config" → "/config"
        tokens = [t if t.startswith("/") else "/" + t for t in path[:1]] + path[1:]
        first = tokens[0]

        if first not in COMMAND_TREE:
            results.write_header(f"/help {' '.join(path)}")
            results.write(f"[red]Unknown command:[/] {first}")
            results.write("Type [cyan]/help[/] for a list of commands.")
            return

        node: dict = COMMAND_TREE[first]
        walked = [first]

        for token in tokens[1:]:
            subs = node.get("subcommands", {})
            if token not in subs:
                break
            node = subs[token]
            walked.append(token)

        header = " ".join(walked)
        results.write_header(f"/help {header}")
        results.write(f"[bold]{node.get('help', '')}[/]")
        results.write("")

        subs = node.get("subcommands")
        if subs:
            results.write("[bold]Subcommands:[/]")
            for name, info in subs.items():
                args = info.get("args", "")
                desc = info.get("help", "")
                full = f"{header} {name}"
                if args:
                    results.write(f"  [cyan]{full} {args}[/]  — {desc}")
                else:
                    results.write(f"  [cyan]{full}[/]  — {desc}")
        else:
            args = node.get("args", "")
            full = header + (f" {args}" if args else "")
            results.write(f"  [cyan]{full}[/]")

        notes = node.get("notes")
        if notes:
            results.write("")
            results.write("[bold]Details:[/]")
            for note in notes:
                results.write(f"  {note}")

    def _write_help_content(self, results) -> None:
        results.write("[cyan]              |                                   [/]")
        results.write("[cyan]             _|_                                  [/]")
        results.write("[cyan]            |   |                                 [/]")
        results.write("[cyan]         ___|___|___                              [/]")
        results.write("[cyan]        /  trawler  \\___,                        [/]")
        results.write("[cyan]  ~~~~~~|_____________|~~~~~~~~~~~~~~~~~~~~~~~~~~[/]")
        results.write("[cyan]  ~  ~  ~  ~  ~  ~ /  ~  ~  ~  ~  ~  ~  ~  ~  ~ [/]")
        results.write("[cyan]                  /\\/\\/\\/\\/\\/\\/\\           [/]")
        results.write("[cyan]                 /               \\              [/]")
        results.write("[cyan]                |  [/][bold yellow]423-55-6789      [/][cyan] |")
        results.write("[cyan]                |  [/][bold red]hunter2          [/][cyan] |")
        results.write("[cyan]                |  [/][bold yellow]4111111111111111 [/][cyan] |")
        results.write("[cyan]                |  [/][bold magenta]ceo@victim-corp  [/][cyan] |")
        results.write("[cyan]                 \\_________________/            [/]")
        results.write("[cyan]  ~  ~  ~  ~  ~  ~  ~  ~  ~  ~  ~  ~  ~  ~  ~  [/]")
        results.write("")
        results.write("[bold]Welcome to Trawler[/]")
        results.write("")
        results.write("Commands:")
        results.write("  [cyan]/search <pattern> [--dir <path>][/]  — regex search; inline flags: (?i) (?m) (?s); supports PDF/DOCX")
        results.write("  [cyan]/rg [-i] [-m] <pattern> [--dir <path>][/]  — ripgrep search (text files only)")
        results.write("  [cyan]/yara [rule-name-glob] [--dir <path>][/]  — YARA scan; glob filters by rule name (* = all)")
        results.write("  [cyan]/semantic <query> [--dir <path>][/]  — vector/semantic search")
        results.write("  [cyan]/index[/]  — embed & index directories for semantic search")
        results.write("  [cyan]/ask <question>[/]  — ask a local or remote LLM about current results")
        results.write("  [cyan]/config [subcommand][/]  — manage configuration (run for details)")
        results.write("  [cyan]/reset[/]  — clear vector store & index history (requires confirmation)")
        results.write("  [cyan]/help[/]  — show this screen")
        results.write("  [cyan]/exit[/]  — quit")
        results.write("")
        results.write("Shortcuts:")
        results.write("  [cyan]ctrl+y[/]  — copy all results to clipboard")
        results.write("  [cyan]ctrl+c[/]  — quit")
        results.write("")
        results.write("Selecting text in the results panel:")
        results.write("  [dim]macOS iTerm2[/]        — [cyan]Cmd+drag[/]")
        results.write("  [dim]macOS Terminal.app[/]  — [cyan]Option+drag[/]  (disable mouse reporting in View menu if needed)")
        results.write("  [dim]Windows Terminal[/]    — [cyan]Shift+drag[/]")
        results.write("  [dim]Linux (most)[/]        — [cyan]Shift+drag[/]  or middle-click to paste")

    def _show_home(self) -> None:
        results = self.query_one(ResultsPanel)
        self.status._reset()
        results.show_search()
        if results._buffer:
            return
        results.clear()
        self._write_help_content(results)

    def _stop_workers(self) -> None:
        """Signal all background workers to stop."""
        self._stop_index.set()
        self._stop_search.set()
        self._stop_ask.set()

    def action_quit(self) -> None:
        if self._indexing:
            self._stop_index.set()
            self._indexing = False
            self.status.set_info("Stopping after current batch… (Ctrl+C again to force quit)")
        elif self._searching:
            self._stop_search.set()
            self._searching = False
            self.status.set_info("Search cancelled")
        else:
            self._stop_workers()
            self.exit()

    def action_focus_command(self) -> None:
        self.query_one(CommandBar).focus_input()

    def action_copy_results(self) -> None:
        if self.query_one(ResultsPanel).copy_to_clipboard():
            self.status.set_done("Results copied to clipboard")
        else:
            self.status.set_error("Copy failed — pbcopy not available")

    def on_command_bar_submitted(self, event: CommandBar.Submitted) -> None:
        self._dispatch_command(event.text)

    def _dispatch_command(self, text: str) -> None:
        if not text:
            self._show_home()
            return

        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd == "/help":
            self._show_help(args.split() if args else None)
            return
        if cmd in ("/exit", "/quit"):
            self._stop_workers()
            self.exit()
            return

        # Config: add/rm report to status bar; list goes to results panel
        if cmd == "/config":
            self._handle_config(args)
            return

        # All search/index commands append to the scrollback and show a running indicator
        results = self.query_one(ResultsPanel)

        if cmd == "/ask":
            if not args:
                results.mark_command_start()
                results.write_header(text)
                results.write("[red]Usage:[/] /ask <question>")
                return
            has_llm = (
                (self.config.llm_model and self.config.llm_backend in ("mlx", "llama-cpp"))
                or (self.config.llm_backend == "remote" and self.config.llm_remote_url)
            )
            if not has_llm:
                results.mark_command_start()
                results.write_header(text)
                results.write(
                    "[yellow]No LLM configured.[/] "
                    "Use [cyan]/config llm <model-id>[/] for a local model or "
                    "[cyan]/config llm remote <url>[/] for a remote endpoint."
                )
                return
            context = results.last_command_context()
            results.mark_command_start()
            results.write_header(text)
            self.status.set_running(f"/ask {args}")
            self._run_ask(args, context)
            return

        results.mark_command_start()
        results.write_header(text)

        if cmd == "/search":
            if not args:
                results.write("[red]Usage:[/] /search <pattern> [--dir <path>]")
                results.write("  Inline flags: [cyan](?i)[/] case-insensitive  [cyan](?m)[/] multiline  [cyan](?s)[/] dot=newline")
                results.write("  Example: [cyan]/search (?i)password[/]  or  [cyan]/search (?i)(?m)^user:[/]")
                results.write("  Supports PDF and DOCX (text-extracted). Type [cyan]/help search[/] for details.")
                return
            self.status.set_running(f"/search {args}")
            self._run_search(cmd, args)
        elif cmd == "/rg":
            if not args:
                results.write("[red]Usage:[/] /rg [options] <pattern> [--dir <path>]")
                results.write("  Flags: [cyan]-i[/] / [cyan]--ignore-case[/]   [cyan]-m[/] / [cyan]--multiline[/]")
                results.write("  Example: [cyan]/rg -i password[/]  or  [cyan]/rg --multiline 'user.*pass'[/]")
                results.write("  Note: text files only — use [cyan]/search[/] for PDF/DOCX. Type [cyan]/help rg[/] for details.")
                return
            self.status.set_running(f"/rg {args}")
            self._run_search(cmd, args)
        elif cmd == "/yara":
            self.status.set_running("/yara")
            self._run_search(cmd, args)
        elif cmd == "/semantic":
            if not args:
                results.write("[red]Usage:[/] /semantic <query>")
                return
            self.status.set_running(f"/semantic {args}")
            self._run_semantic_search(args)
        elif cmd == "/reset":
            self.push_screen(ConfirmResetModal(), self._on_reset_confirmed)
            return
        elif cmd == "/index":
            if self.config.max_file_bytes is None:
                self.push_screen(FileSizeLimitModal(), self._on_file_size_limit_set)
            else:
                self._check_extensions_then_index()
        else:
            results.write(f"[red]Unknown command:[/] {text}")
            results.write("Type [cyan]/help[/] to see available commands.")

    @staticmethod
    def _parse_dir_flag(args: str) -> tuple[str, str | None]:
        """Strip --dir <path> from args and return (cleaned_args, dir_path | None)."""
        import shlex
        try:
            parts = shlex.split(args)
        except ValueError:
            return args, None
        cleaned: list[str] = []
        dir_path: str | None = None
        i = 0
        while i < len(parts):
            if parts[i] == "--dir" and i + 1 < len(parts):
                dir_path = parts[i + 1]
                i += 2
            else:
                cleaned.append(parts[i])
                i += 1
        return shlex.join(cleaned), dir_path

    @work(thread=True)
    def _run_search(self, cmd: str, args: str) -> None:
        self._stop_search.clear()
        self._searching = True
        results = self.query_one(ResultsPanel)
        match_count = 0

        def emit(line: str) -> None:
            nonlocal match_count
            match_count += 1
            self.call_from_thread(results.write, line)

        clean_args, dir_filter = self._parse_dir_flag(args)

        if dir_filter is not None:
            p = Path(dir_filter)
            if not p.exists():
                self.call_from_thread(results.write, f"[red]Path not found:[/] {dir_filter}")
                self.call_from_thread(self.status.set_error, f"{cmd} — path not found")
                self._searching = False
                return
            dirs = [dir_filter]
        else:
            dirs = self.config.directories

        def on_progress(files_scanned: int) -> None:
            noun = "match" if match_count == 1 else "matches"
            self.call_from_thread(
                self.status.set_running,
                f"{cmd} — {files_scanned:,} files scanned, {match_count} {noun}…",
            )

        if cmd == "/search":
            for line in basic.search(
                clean_args, dirs,
                stop_event=self._stop_search,
                on_progress=on_progress,
            ):
                emit(line)
        elif cmd == "/rg":
            for line in ripgrep.search(clean_args, dirs):
                emit(line)
        elif cmd == "/yara":
            pattern = clean_args.strip() if clean_args.strip() else None
            for line in yara_scan.scan(pattern, dirs, rules_dir=self.config.rules_dir):
                emit(line)

        self._searching = False
        if self._stop_search.is_set():
            noun = "match" if match_count == 1 else "matches"
            self.call_from_thread(
                self.status.set_info,
                f"{cmd} cancelled — {match_count} {noun} so far",
            )
        else:
            noun = "result" if match_count == 1 else "results"
            self.call_from_thread(self.status.set_done, f"{cmd} — {match_count} {noun}")

    @work(thread=True)
    def _run_semantic_search(self, args: str) -> None:
        results = self.query_one(ResultsPanel)
        count = 0

        def emit(line: str) -> None:
            nonlocal count
            count += 1
            self.call_from_thread(results.write, line)

        filter_dir: str | None = None
        query = args
        if "--dir" in args:
            parts = args.split("--dir", 1)
            query = parts[0].strip()
            filter_dir = parts[1].strip()

        for line in semantic_search.search(
            query,
            model_name=self.config.embedding_model,
            filter_dir=filter_dir,
        ):
            emit(line)

        noun = "result" if count == 1 else "results"
        self.call_from_thread(self.status.set_done, f"/semantic — {count} {noun}")

    @work(thread=True)
    def _run_ask(self, question: str, context: str) -> None:
        import time
        from .search.local_llm import ask as llm_ask, ensure_model_cached

        self._stop_ask.clear()
        results = self.query_one(ResultsPanel)
        cmd_bar = self.query_one(CommandBar)
        self.call_from_thread(cmd_bar.set_busy, True)
        self.call_from_thread(results.start_stream)

        try:
            # --- download phase (mlx only; no-op for llama-cpp / remote) ---
            if self.config.llm_backend == "mlx" and self.config.llm_model:
                def on_download(text: str) -> None:
                    self.call_from_thread(results.update_stream, text)

                ready, err = ensure_model_cached(self.config.llm_model, on_download)
                if not ready or self._stop_ask.is_set():
                    self.call_from_thread(results.end_stream, "")
                    if err:
                        for line in err.splitlines():
                            self.call_from_thread(results.write, line)
                    if not self._stop_ask.is_set():
                        self.call_from_thread(self.status.set_error, "Model download failed")
                    return

            # --- inference / streaming phase ---
            accumulated = ""
            had_meta = False
            last_repaint = 0.0
            REPAINT_INTERVAL = 0.05  # max 20 repaints/sec

            for token in llm_ask(question, context, self.config):
                if self._stop_ask.is_set():
                    break
                if token.startswith("["):
                    # Error or status message — write directly to the persistent
                    # log so it isn't lost when the streaming overlay closes.
                    had_meta = True
                    self.call_from_thread(results.write, token)
                else:
                    accumulated += token
                    now = time.monotonic()
                    if now - last_repaint >= REPAINT_INTERVAL:
                        self.call_from_thread(results.update_stream, accumulated)
                        last_repaint = now

            self.call_from_thread(results.end_stream, accumulated)
            if not accumulated and not had_meta:
                self.call_from_thread(results.write, "[dim]No response generated.[/]")
            self.call_from_thread(self.status.set_done, "/ask complete")
        except Exception as e:
            from rich.markup import escape
            self.call_from_thread(results.end_stream, "")
            self.call_from_thread(results.write, f"[red]Error:[/] {escape(str(e))}")
            self.call_from_thread(self.status.set_error, "/ask failed")
        finally:
            self.call_from_thread(cmd_bar.set_busy, False)

    @work(thread=True)
    def _run_index(self) -> None:
        import threading
        import time

        results = self.query_one(ResultsPanel)
        sidebar = self.query_one(DirectorySidebar)

        def emit(line: str) -> None:
            self.call_from_thread(results.write, line)

        if not self.config.directories:
            self.call_from_thread(
                self.status.set_error, "No directories configured — use /config path add <path>"
            )
            return

        self._indexing = True
        self._stop_index.clear()

        from collections import deque
        import math

        def _fmt_eta(secs: float) -> str:
            s = int(secs)
            if s < 60:
                return f"{s}s"
            m, s = divmod(s, 60)
            if m < 60:
                return f"{m}m {s}s"
            h, m = divmod(m, 60)
            return f"{h}h {m}m"

        start_time = time.perf_counter()
        _progress: dict = {"done": 0, "total": 0, "eta": None}
        _ticker_stop = threading.Event()
        _batch_times: deque[float] = deque(maxlen=5)
        _last_batch_t = [start_time]

        def _ticker() -> None:
            while not _ticker_stop.wait(timeout=1.0):
                elapsed = int(time.perf_counter() - start_time)
                done, total, eta = _progress["done"], _progress["total"], _progress["eta"]
                files_str = f"{done}/{total} files — " if total else ""
                eta_str = f" — ETA {_fmt_eta(eta)}" if eta is not None else ""
                self.call_from_thread(
                    self.status.set_running,
                    f"/index — {files_str}{elapsed}s elapsed{eta_str}",
                )

        threading.Thread(target=_ticker, daemon=True).start()

        def on_progress(done: int, total: int) -> None:
            now = time.perf_counter()
            _batch_times.append(now - _last_batch_t[0])
            _last_batch_t[0] = now
            remaining_batches = math.ceil((total - done) / semantic_search.FILE_BATCH_SIZE)
            avg = sum(_batch_times) / len(_batch_times)
            _progress["done"] = done
            _progress["total"] = total
            _progress["eta"] = avg * remaining_batches if remaining_batches > 0 else 0.0
            self.call_from_thread(sidebar.refresh_directories)

        semantic_search.index(
            self.config.directories,
            model_name=self.config.embedding_model,
            emit=emit,
            on_progress=on_progress,
            stop_event=self._stop_index,
            max_file_bytes=self.config.max_file_bytes or 0,
            index_extensions=self.config.index_extensions or None,
        )

        _ticker_stop.set()
        self._indexing = False

        elapsed = time.perf_counter() - start_time
        minutes, secs = divmod(int(elapsed), 60)
        time_str = f"{minutes}m {secs}s" if minutes else f"{secs}s"

        self.index_state = IndexState()
        self.call_from_thread(sidebar.refresh_sizes)
        self.call_from_thread(self.status.set_done, f"/index complete — {time_str}")

    def _handle_config(self, args: str) -> None:
        from .config import DEFAULT_INDEX_EXTENSIONS, DEFAULT_SKIP_EXTENSIONS
        parts = args.split(maxsplit=1)
        sub = parts[0].lower() if parts else ""
        rest = parts[1].strip() if len(parts) > 1 else ""

        results = self.query_one(ResultsPanel)

        # /config or /config list — show full summary
        if not sub or sub == "list":
            results.show_utility()
            results.write_header("/config")
            results.write("[bold]Directories:[/]")
            if self.config.directories:
                for d in self.config.directories:
                    results.write(f"  [cyan]{d}[/]")
            else:
                results.write("  [dim]none configured[/]")
            results.write("")
            results.write("[bold]Settings:[/]")
            limit = self.config.max_file_bytes
            if limit is None:
                limit_str = "[dim]not set (will prompt on /index)[/]"
            elif limit == 0:
                limit_str = "[dim]no limit[/]"
            else:
                from .widgets.sidebar import _fmt_size
                limit_str = _fmt_size(limit)
            results.write(f"  File size limit:  {limit_str}")
            results.write(f"  Embedding model:  [dim]{self.config.embedding_model}[/]")
            from .search.yara_scan import DEFAULT_RULES_DIR
            rules_str = self.config.rules_dir if self.config.rules_dir else f"[dim]{DEFAULT_RULES_DIR} (default)[/]"
            results.write(f"  YARA rules dir:   {rules_str}")
            proxy_str = f"[dim]{self.config.proxy}[/]" if self.config.proxy else "[dim]none[/]"
            results.write(f"  Proxy:            {proxy_str}")
            results.write("")
            exts = self.config.index_extensions
            results.write(f"[bold]Indexed extensions ({len(exts)}):[/]")
            results.write("  " + "  ".join(f"[green]{e}[/]" for e in sorted(exts)) if exts else "  [dim]none[/]")
            skipped = self.config.skip_extensions
            results.write(f"[bold]Skipped extensions ({len(skipped)}):[/]")
            results.write("  " + "  ".join(f"[dim]{e}[/]" for e in sorted(skipped)) if skipped else "  [dim]none[/]")
            results.write("")
            results.write("[bold]Commands:[/]")
            results.write("  [cyan]/config path[/]             — manage watched directories")
            results.write("  [cyan]/config filesize <value>[/] — set max file size (e.g. 500KB, 2MB, 0=unlimited)")
            results.write("  [cyan]/config ext[/]              — manage file extension filters")
            results.write("  [cyan]/config rules[/]            — set custom YARA rules directory")
            results.write("  [cyan]/config proxy[/]            — set HTTP/HTTPS proxy")
            results.write("  [cyan]/config llm[/]              — view/configure LLM for /ask")
            results.write("  [dim]type any subcommand alone for details[/]")
            return

        if sub == "path":
            path_parts = rest.split(maxsplit=1)
            path_sub = path_parts[0].lower() if path_parts else ""
            path_val = path_parts[1].strip() if len(path_parts) > 1 else ""

            if not path_sub:
                results.show_utility()
                results.write_header("/config path")
                results.write("[bold]Watched directories:[/]")
                if self.config.directories:
                    for i, d in enumerate(self.config.directories, 1):
                        results.write(f"  [dim]{i}.[/]  [cyan]{d}[/]")
                else:
                    results.write("  [dim]none configured[/]")
                results.write("")
                results.write("[bold]Commands:[/]")
                results.write("  [cyan]/config path add <path>[/]  — add a watched directory")
                results.write("  [cyan]/config path rm <n|path>[/] — remove by number or full path")

            elif path_sub == "add":
                if path_val:
                    self._add_directory(path_val)
                else:
                    self.status.set_error("/config path add — usage: /config path add <path>")

            elif path_sub == "rm":
                if not path_val:
                    self.status.set_error("/config path rm — usage: /config path rm <n> or /config path rm <path>")
                    return
                # Accept a 1-based index as shorthand (e.g. /config path rm 1)
                if path_val.isdigit():
                    idx = int(path_val) - 1
                    if 0 <= idx < len(self.config.directories):
                        removed = self.config.directories[idx]
                        self.config.remove_directory(removed)
                        self.query_one(DirectorySidebar).refresh_directories()
                        self.status.set_done(f"Removed {removed}")
                    else:
                        self.status.set_error(f"No directory at index {path_val} — use /config path to list")
                elif path_val in self.config.directories:
                    self.config.remove_directory(path_val)
                    self.query_one(DirectorySidebar).refresh_directories()
                    self.status.set_done(f"Removed {path_val}")
                else:
                    self.status.set_error(f"Not found: {path_val}")

            else:
                self.status.set_error(f"Unknown: /config path {path_sub} — try add, rm")

        elif sub == "filesize":
            if not rest:
                self.status.set_error("/config filesize — usage: /config filesize <value> (e.g. 500KB, 2MB, 0)")
                return
            parsed = _parse_file_size(rest)
            if parsed is None:
                self.status.set_error(f"Could not parse size: {rest}")
                return
            self.config.max_file_bytes = parsed
            self.config.save()
            from .widgets.sidebar import _fmt_size
            label = "no limit" if parsed == 0 else _fmt_size(parsed)
            self.query_one(DirectorySidebar).refresh_directories()
            self.status.set_done(f"File size limit set to {label}")

        elif sub == "ext":
            ext_parts = rest.split(maxsplit=1)
            ext_sub = ext_parts[0].lower() if ext_parts else ""
            ext_val = ext_parts[1].strip().lower() if len(ext_parts) > 1 else ""

            if not ext_sub:
                results.show_utility()
                results.write_header("/config ext")
                results.write("[bold]Manage file extension filters[/]")
                results.write("")
                results.write("[bold]Commands:[/]")
                results.write("  [cyan]/config ext list[/]        — show current index/skip extension lists")
                results.write("  [cyan]/config ext add <.ext>[/]  — whitelist an extension")
                results.write("  [cyan]/config ext rm <.ext>[/]   — move extension to skip list")
                results.write("  [cyan]/config ext reset[/]       — restore default extension lists")

            elif ext_sub == "list":
                results.show_utility()
                results.write_header("/config ext list")
                exts = self.config.index_extensions
                results.write(f"[bold]Indexed ({len(exts)}):[/]")
                results.write("  " + "  ".join(f"[green]{e}[/]" for e in sorted(exts)) if exts else "  [dim]none[/]")
                skipped = self.config.skip_extensions
                results.write(f"[bold]Skipped ({len(skipped)}):[/]")
                results.write("  " + "  ".join(f"[dim]{e}[/]" for e in sorted(skipped)) if skipped else "  [dim]none[/]")

            elif ext_sub == "add":
                if not ext_val:
                    self.status.set_error("/config ext add — usage: /config ext add <.ext>")
                    return
                if not ext_val.startswith("."):
                    ext_val = "." + ext_val
                self.config.skip_extensions = [e for e in self.config.skip_extensions if e != ext_val]
                if ext_val not in self.config.index_extensions:
                    self.config.index_extensions.append(ext_val)
                self.config.save()
                self.query_one(DirectorySidebar).refresh_directories()
                self.status.set_done(f"Whitelisted {ext_val}")

            elif ext_sub == "rm":
                if not ext_val:
                    self.status.set_error("/config ext rm — usage: /config ext rm <.ext>")
                    return
                if not ext_val.startswith("."):
                    ext_val = "." + ext_val
                self.config.index_extensions = [e for e in self.config.index_extensions if e != ext_val]
                if ext_val not in self.config.skip_extensions:
                    self.config.skip_extensions.append(ext_val)
                self.config.save()
                self.query_one(DirectorySidebar).refresh_directories()
                self.status.set_done(f"Skipping {ext_val}")

            elif ext_sub == "reset":
                self.config.index_extensions = list(DEFAULT_INDEX_EXTENSIONS)
                self.config.skip_extensions = list(DEFAULT_SKIP_EXTENSIONS)
                self.config.save()
                self.query_one(DirectorySidebar).refresh_directories()
                self.status.set_done("Extensions reset to defaults")

            else:
                self.status.set_error(f"Unknown: /config ext {ext_sub} — try list, add, rm, reset")

        elif sub == "proxy":
            if not rest:
                results.show_utility()
                results.write_header("/config proxy")
                proxy_str = f"[dim]{self.config.proxy}[/]" if self.config.proxy else "[dim]none[/]"
                results.write(f"  Current proxy:  {proxy_str}")
                results.write("")
                results.write("[bold]Commands:[/]")
                results.write("  [cyan]/config proxy <url>[/]   — set HTTP/HTTPS proxy (e.g. http://proxy:8080)")
                results.write("  [cyan]/config proxy reset[/]   — clear proxy setting")
                return
            if rest.lower() == "reset":
                self.config.proxy = None
                self.config.save()
                self._apply_proxy(None)
                self.status.set_done("Proxy cleared")
            else:
                self.config.proxy = rest
                self.config.save()
                self._apply_proxy(rest)
                self.status.set_done(f"Proxy set to {rest}")

        elif sub == "rules":
            if not rest:
                results.show_utility()
                results.write_header("/config rules")
                from .search.yara_scan import DEFAULT_RULES_DIR
                rules_str = self.config.rules_dir if self.config.rules_dir else f"[dim]{DEFAULT_RULES_DIR} (default)[/]"
                results.write(f"  Current rules dir:  {rules_str}")
                results.write("")
                results.write("[bold]Commands:[/]")
                results.write("  [cyan]/config rules <path>[/]   — set custom YARA rules directory")
                results.write("  [cyan]/config rules reset[/]    — revert to bundled rules directory")
                return
            if rest.lower() == "reset":
                self.config.rules_dir = None
                self.config.save()
                self.status.set_done("YARA rules directory reset to default")
            else:
                p = Path(rest)
                if not p.is_dir():
                    self.status.set_error(f"Not a valid directory: {rest}")
                    return
                self.config.rules_dir = str(p)
                self.config.save()
                self.status.set_done(f"YARA rules directory set to {rest}")

        elif sub == "llm":
            self._handle_config_llm(rest, results)

        else:
            self.status.set_error(f"Unknown subcommand: /config {sub} — type /config for help")

    def _handle_config_llm(self, args: str, results) -> None:
        """Handle /config llm <subcommand>."""
        llm_parts = args.split(maxsplit=1)
        llm_sub = llm_parts[0].lower() if llm_parts else ""
        llm_rest = llm_parts[1].strip() if len(llm_parts) > 1 else ""

        if not llm_sub:
            # Show current LLM config
            results.show_utility()
            results.write_header("/config llm")
            backend = self.config.llm_backend
            model = self.config.llm_model or "[dim]none[/]"
            remote_url = self.config.llm_remote_url or "[dim]none[/]"
            api_key = "***" if self.config.llm_remote_api_key else "[dim]none[/]"
            results.write(f"  Backend:     [cyan]{backend}[/]")
            results.write(f"  Model:       {model}")
            results.write(f"  Remote URL:  {remote_url}")
            results.write(f"  API key:     {api_key}")
            results.write(f"  Context:     {self.config.llm_context_tokens} tokens")
            sys_prompt = self.config.llm_system_prompt
            sys_display = f"[dim]{sys_prompt[:60]}{'…' if len(sys_prompt) > 60 else ''}[/]" if sys_prompt else "[dim]none[/]"
            results.write(f"  Sys prompt:  {sys_display}")
            results.write("")
            results.write("[bold]Local — Apple Silicon (mlx-lm):[/]")
            results.write("  [cyan]/config llm mlx <hf-repo-id>[/]")
            results.write("  [dim]e.g. mlx-community/Mistral-7B-Instruct-v0.2-4bit[/]")
            results.write("  [dim]Downloaded automatically to ~/.cache/huggingface/hub/[/]")
            results.write("")
            results.write("[bold]Local — cross-platform (llama-cpp GGUF):[/]")
            results.write("  [cyan]/config llm gguf <path-to-.gguf>[/]")
            results.write("  [dim]e.g. ~/models/mistral-7b-instruct-v0.2.Q4_K_M.gguf[/]")
            results.write("  [dim]Get GGUF files: huggingface.co/bartowski  or  huggingface.co/TheBloke[/]")
            results.write("")
            results.write("[bold]Remote (any OpenAI-compatible endpoint):[/]")
            results.write("  [cyan]/config llm remote <url>[/]             — base URL (e.g. http://localhost:11434/v1)")
            results.write("  [cyan]/config llm remote <url> <model>[/]     — with model name")
            results.write("  [cyan]/config llm apikey <key>[/]             — API key if required")
            results.write("")
            results.write("[bold]Other:[/]")
            results.write("  [cyan]/config llm systemprompt <text>[/]      — set system prompt")
            results.write("  [cyan]/config llm systemprompt reset[/]       — remove system prompt")
            results.write("  [cyan]/config llm reset[/]                    — disable LLM")
            return

        if llm_sub == "reset":
            self.config.llm_model = None
            self.config.llm_remote_url = None
            self.config.llm_remote_api_key = None
            self.config.llm_backend = "mlx"
            self.config.save()
            self.status.set_done("LLM disabled")

        elif llm_sub == "remote":
            if not llm_rest:
                self.status.set_error("/config llm remote — usage: /config llm remote <url> [<model>]")
                return
            url_parts = llm_rest.split(maxsplit=1)
            self.config.llm_remote_url = url_parts[0]
            if len(url_parts) > 1:
                self.config.llm_model = url_parts[1]
            self.config.llm_backend = "remote"
            self.config.save()
            model_info = f" (model: {self.config.llm_model})" if self.config.llm_model else ""
            self.status.set_done(f"Remote LLM set to {self.config.llm_remote_url}{model_info}")

        elif llm_sub == "apikey":
            if not llm_rest:
                self.status.set_error("/config llm apikey — usage: /config llm apikey <key>")
                return
            self.config.llm_remote_api_key = llm_rest
            self.config.save()
            self.status.set_done("API key saved")

        elif llm_sub == "systemprompt":
            if not llm_rest:
                self.status.set_error("/config llm systemprompt — usage: /config llm systemprompt <text> | reset")
                return
            if llm_rest.lower() == "reset":
                self.config.llm_system_prompt = None
                self.config.save()
                self.status.set_done("System prompt cleared")
            else:
                self.config.llm_system_prompt = llm_rest
                self.config.save()
                self.status.set_done("System prompt set")

        elif llm_sub == "mlx":
            if not llm_rest:
                self.status.set_error("/config llm mlx — usage: /config llm mlx <hf-repo-id>")
                return
            from .search.local_llm import _detect_backend
            detected = _detect_backend()
            backend = "mlx" if detected == "mlx" else (detected or "mlx")
            self.config.llm_model = llm_rest
            self.config.llm_backend = backend
            self.config.save()
            suffix = "" if backend == "mlx" else f" [dim](mlx not found — will use {backend})[/]"
            self.status.set_done(f"Model set to {llm_rest}{suffix}")

        elif llm_sub == "gguf":
            if not llm_rest:
                self.status.set_error("/config llm gguf — usage: /config llm gguf <path-to-.gguf>")
                return
            from pathlib import Path
            from .search.local_llm import _detect_backend
            p = Path(llm_rest).expanduser().resolve()
            detected = _detect_backend()
            backend = "llama-cpp" if detected == "llama-cpp" else (detected or "llama-cpp")
            self.config.llm_model = str(p)
            self.config.llm_backend = backend
            self.config.save()
            suffix = "" if backend == "llama-cpp" else f" [dim](llama-cpp not found — will use {backend})[/]"
            self.status.set_done(f"GGUF model set to {p.name}{suffix}")

        else:
            self.status.set_error(
                f"Unknown: /config llm {llm_sub} — try mlx, gguf, remote, apikey, systemprompt, reset"
            )

    def _check_extensions_then_index(self) -> None:
        self.status.set_running("/index — scanning file types…")
        self._scan_unknown_extensions()

    @work(thread=True)
    def _scan_unknown_extensions(self) -> None:
        known = set(self.config.index_extensions) | set(self.config.skip_extensions)
        unknown: set[str] = set()
        for d in self.config.directories:
            p = Path(d)
            if p.is_dir():
                for fp in p.rglob("*"):
                    if fp.is_file():
                        ext = fp.suffix.lower()
                        if ext and ext not in known:
                            unknown.add(ext)
        self.call_from_thread(self._on_extensions_scanned, sorted(unknown))

    def _on_extensions_scanned(self, unknown: list[str]) -> None:
        if unknown:
            self.push_screen(ExtensionModal(unknown), self._on_extension_modal_result)
        else:
            self.status.set_running("/index")
            self._run_index()

    def _on_extension_modal_result(self, result) -> None:
        if result is None:
            self.status.set_info("Index cancelled")
            return
        to_whitelist, to_skip = result
        for ext in to_whitelist:
            if ext not in self.config.index_extensions:
                self.config.index_extensions.append(ext)
        for ext in to_skip:
            if ext not in self.config.skip_extensions:
                self.config.skip_extensions.append(ext)
        self.config.save()
        self.query_one(DirectorySidebar).refresh_directories()
        self.status.set_running("/index")
        self._run_index()

    def _add_directory(self, path: str) -> None:
        if not Path(path).is_dir():
            self.status.set_error(f"Not a valid directory: {path}")
            return
        self.config.add_directory(path)
        self.query_one(DirectorySidebar).refresh_directories()
        self.status.set_done(f"Added {path}")

    def _on_reset_confirmed(self, confirmed: bool) -> None:
        if not confirmed:
            self.status.set_info("Reset cancelled")
            return
        import shutil
        from .search.semantic import CHROMA_DIR
        from .index_state import STATE_FILE
        try:
            if CHROMA_DIR.exists():
                shutil.rmtree(CHROMA_DIR)
            if STATE_FILE.exists():
                STATE_FILE.unlink()
            self.index_state = IndexState()
            self.query_one(DirectorySidebar).refresh_sizes()
            self.status.set_done("Vector store and index history cleared")
        except OSError as e:
            self.status.set_error(f"Reset failed: {e}")

    def _on_file_size_limit_set(self, result: int | None) -> None:
        if result is None:
            self.status.set_info("Index cancelled")
            return
        # 0 = no limit (user chose unlimited); >0 = bytes limit
        self.config.max_file_bytes = result
        self.config.save()
        limit_str = "no limit" if result == 0 else f"{result // 1024} KB"
        self.status.set_info(f"File size limit set: {limit_str}")
        self.query_one(DirectorySidebar).refresh_directories()
        self._check_extensions_then_index()
