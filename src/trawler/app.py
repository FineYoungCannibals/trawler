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
        self.index_state = IndexState()
        self._indexing = False
        self._stop_index = threading.Event()

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
        self._show_help()
        self.status.set_hint("Press Enter to return home")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "cmd-input":
            if event.value:
                self.status._reset()
            else:
                self.status.set_hint("Press Enter to return home")

    def _show_help(self) -> None:
        results = self.query_one(ResultsPanel)
        self.status._reset()
        results.clear()
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
        results.write("  [cyan]/search <pattern>[/]  — regex string search")
        results.write("  [cyan]/rg [opts] <pattern>[/]  — ripgrep search")
        results.write("  [cyan]/yara [rule-glob][/]  — run YARA rules (* = all)")
        results.write("  [cyan]/semantic <query> [--dir <path>][/]  — vector/semantic search")
        results.write("  [cyan]/index[/]  — embed & index directories for semantic search")
        results.write("  [cyan]/config [subcommand][/]  — manage configuration (run for details)")
        results.write("  [cyan]/reset[/]  — clear vector store & index history (requires confirmation)")
        results.write("  [cyan]/help[/]  — show this screen")
        results.write("  [cyan]/exit[/]  — quit")
        results.write("")
        results.write("Shortcuts:")
        results.write("  [cyan]ctrl+y[/]  — copy all results to clipboard")
        results.write("  [cyan]ctrl+c[/]  — quit")

    def action_quit(self) -> None:
        if self._indexing:
            self._stop_index.set()
            self._indexing = False
            self.status.set_info("Stopping after current batch… (Ctrl+C again to force quit)")
        else:
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
            self._show_help()
            return

        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd == "/help":
            self._show_help()
            return
        if cmd in ("/exit", "/quit"):
            self.exit()
            return

        # Config: add/rm report to status bar; list goes to results panel
        if cmd == "/config":
            self._handle_config(args)
            return

        # All search/index commands clear results and show a running indicator
        results = self.query_one(ResultsPanel)
        results.clear()
        results.write_header(text)

        if cmd == "/search":
            if not args:
                results.write("[red]Usage:[/] /search <pattern>")
                return
            self.status.set_running(f"/search {args}")
            self._run_search(cmd, args)
        elif cmd == "/rg":
            if not args:
                results.write("[red]Usage:[/] /rg [options] <pattern>")
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

    @work(thread=True)
    def _run_search(self, cmd: str, args: str) -> None:
        results = self.query_one(ResultsPanel)
        count = 0

        def emit(line: str) -> None:
            nonlocal count
            count += 1
            self.call_from_thread(results.write, line)

        dirs = self.config.directories

        if cmd == "/search":
            for line in basic.search(args, dirs):
                emit(line)
        elif cmd == "/rg":
            for line in ripgrep.search(args, dirs):
                emit(line)
        elif cmd == "/yara":
            pattern = args.strip() if args.strip() else None
            for line in yara_scan.scan(pattern, dirs, rules_dir=self.config.rules_dir):
                emit(line)

        noun = "result" if count == 1 else "results"
        self.call_from_thread(self.status.set_done, f"{cmd} — {count} {noun}")

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
    def _run_index(self) -> None:
        import threading
        import time

        results = self.query_one(ResultsPanel)
        sidebar = self.query_one(DirectorySidebar)

        def emit(line: str) -> None:
            self.call_from_thread(results.write, line)

        if not self.config.directories:
            self.call_from_thread(
                self.status.set_error, "No directories configured — use /config add <path>"
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
            results.clear()
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
            results.write("")
            exts = self.config.index_extensions
            results.write(f"[bold]Indexed extensions ({len(exts)}):[/]")
            results.write("  " + "  ".join(f"[green]{e}[/]" for e in sorted(exts)) if exts else "  [dim]none[/]")
            skipped = self.config.skip_extensions
            results.write(f"[bold]Skipped extensions ({len(skipped)}):[/]")
            results.write("  " + "  ".join(f"[dim]{e}[/]" for e in sorted(skipped)) if skipped else "  [dim]none[/]")
            results.write("")
            results.write("[bold]Commands:[/]")
            results.write("  [cyan]/config add <path>[/]         — add a watched directory")
            results.write("  [cyan]/config rm <path>[/]          — remove a watched directory")
            results.write("  [cyan]/config filesize <value>[/]   — set max file size (e.g. 500KB, 2MB, 0=unlimited)")
            results.write("  [cyan]/config ext list[/]           — show extension whitelist & skiplist")
            results.write("  [cyan]/config ext add <.ext>[/]     — whitelist an extension")
            results.write("  [cyan]/config ext rm <.ext>[/]      — move extension to skiplist")
            results.write("  [cyan]/config ext reset[/]          — reset extensions to defaults")
            results.write("  [cyan]/config rules <path>[/]       — set custom YARA rules directory")
            results.write("  [cyan]/config rules reset[/]        — revert to bundled rules directory")
            return

        if sub == "add":
            if rest:
                self._add_directory(rest)
            else:
                self.status.set_error("/config add — usage: /config add <path>")

        elif sub == "rm":
            if not rest:
                self.status.set_error("/config rm — usage: /config rm <path>")
                return
            if rest in self.config.directories:
                self.config.remove_directory(rest)
                self.query_one(DirectorySidebar).refresh_directories()
                self.status.set_done(f"Removed {rest}")
            else:
                self.status.set_error(f"Not found: {rest}")

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

            if ext_sub == "list" or not ext_sub:
                results.clear()
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

        elif sub == "rules":
            if not rest:
                self.status.set_error("/config rules — usage: /config rules <path> | reset")
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

        else:
            self.status.set_error(f"Unknown subcommand: /config {sub} — type /config for help")

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
