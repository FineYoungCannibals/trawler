from __future__ import annotations

import threading
from pathlib import Path

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label, ListItem, ListView, Static

from ..config import TrawlerConfig
from ..index_state import IndexState
from ..search.semantic import CHROMA_DIR


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def _dir_size(path: str) -> int:
    return sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file())


def _chroma_size() -> int:
    if not CHROMA_DIR.exists():
        return 0
    return sum(f.stat().st_size for f in CHROMA_DIR.rglob("*") if f.is_file())


class DirectoryItem(ListItem):
    def __init__(
        self,
        path: str,
        status: dict[str, int],
        disk_size: int | None,
        max_file_bytes: int = 0,
    ) -> None:
        super().__init__()
        self.path = path
        self.status = status
        self.disk_size = disk_size
        self.max_file_bytes = max_file_bytes

    def compose(self) -> ComposeResult:
        eligible = self.status.get("eligible", 0)
        indexed = self.status.get("indexed", 0)
        total = self.status.get("total", 0)
        oversized = self.status.get("oversized", 0)

        if total == 0:
            indicator = "[dim]○ empty[/]"
        elif eligible == 0:
            indicator = "[dim]○ no eligible files[/]"
        elif indexed == eligible:
            indicator = f"[green]● {indexed} indexed[/]"
        elif indexed == 0:
            indicator = f"[yellow]○ 0/{eligible} eligible[/]"
        else:
            indicator = f"[yellow]○ {indexed}/{eligible} indexed[/]"

        size_str = _fmt_size(self.disk_size) if self.disk_size is not None else "[dim]…[/]"
        display_path = self.path if len(self.path) <= 38 else "…" + self.path[-37:]

        lines = [display_path, f"  {indicator}  [dim]{size_str}[/]"]

        if oversized and self.max_file_bytes:
            lines.append(f"  [yellow]⚠ {oversized} skipped (over size limit)[/]")

        type_skipped_exts: dict[str, int] = self.status.get("type_skipped_exts", {})
        if type_skipped_exts:
            sorted_exts = sorted(type_skipped_exts.items(), key=lambda x: -x[1])
            shown = sorted_exts[:3]
            remainder = len(sorted_exts) - 3
            ext_parts = "  ".join(
                f"[dim]{(ext if ext else '(no ext)')}({n})[/]"
                for ext, n in shown
            )
            if remainder > 0:
                ext_parts += f"  [dim]+{remainder} more[/]"
            lines.append(f"  [dim]skip:[/] {ext_parts}")

        yield Label("\n".join(lines), markup=True)


class DirectorySidebar(Widget):
    DEFAULT_CSS = """
    DirectorySidebar {
        width: 42;
        layout: vertical;
        border: solid $primary;
        padding: 0 1;
    }
    DirectorySidebar .sidebar-title {
        text-style: bold;
        margin-bottom: 1;
    }
    DirectorySidebar .no-dirs {
        color: $text-muted;
        text-style: italic;
        height: 1fr;
    }
    DirectorySidebar ListView {
        height: 1fr;
    }
    DirectorySidebar DirectoryItem {
        height: auto;
    }
    DirectorySidebar .stats-footer {
        height: 3;
        border-top: solid $panel;
        padding: 1 0 0 0;
        color: $text-muted;
    }
    """

    def __init__(self, config: TrawlerConfig) -> None:
        super().__init__()
        self.config = config
        self._dir_sizes: dict[str, int | None] = {}
        self._db_size: int | None = None

    def on_mount(self) -> None:
        self._start_size_compute()

    def _start_size_compute(self) -> None:
        self._dir_sizes = {d: None for d in self.config.directories}
        self._db_size = None
        threading.Thread(target=self._bg_compute_sizes, daemon=True).start()

    def _bg_compute_sizes(self) -> None:
        sizes: dict[str, int | None] = {}
        for d in self.config.directories:
            try:
                sizes[d] = _dir_size(d)
            except OSError:
                sizes[d] = None
        try:
            db = _chroma_size()
        except OSError:
            db = None
        self._dir_sizes = sizes
        self._db_size = db
        self.app.call_from_thread(self.recompose)

    def refresh_sizes(self) -> None:
        """Recompute disk sizes in background (call after indexing completes)."""
        self._start_size_compute()

    def _get_status(self) -> dict[str, dict[str, int]]:
        return IndexState().dir_status(
            self.config.directories,
            max_file_bytes=self.config.max_file_bytes or None,
            index_extensions=self.config.index_extensions or None,
        )

    def compose(self) -> ComposeResult:
        yield Static("Directories", classes="sidebar-title")
        statuses = self._get_status()
        if self.config.directories:
            limit = self.config.max_file_bytes or 0
            items = [
                DirectoryItem(d, statuses.get(d, {}), self._dir_sizes.get(d), limit)
                for d in self.config.directories
            ]
            yield ListView(*items)
        else:
            yield Static("No directories.\nUse /config add <path>", classes="no-dirs")

        if self._db_size is None:
            db_str = "[dim]…[/]"
        elif self._db_size == 0:
            db_str = "[dim]none[/]"
        else:
            db_str = _fmt_size(self._db_size)
        yield Static(f"[dim]ChromaDB:[/] {db_str}", classes="stats-footer", markup=True)

    def refresh_directories(self) -> None:
        """Re-render the directory list (uses cached disk sizes)."""
        self.app.call_later(self.recompose)
